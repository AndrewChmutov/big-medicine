from __future__ import annotations

import itertools
import operator
import os
import traceback
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from cassandra.cluster import Session
from cassandra.cqlengine.connection import (
    Cluster,
    register_connection,
    set_default_connection,
)
from cassandra.query import BoundStatement, PreparedStatement
from fastapi import FastAPI, Request

from big_medicine.core.client.model import Cassandra
from big_medicine.core.server.message import (
    MedicineEntry,
    MedicineReservations,
    MedicineResponse,
    ReservationEntryItem,
    ReservationResponse,
    ReservationsResponse,
    ResponseItem,
    ResponseType,
    UpdateReservation,
)
from big_medicine.core.server.model import (
    Medicine,
    Reservation,
)
from big_medicine.utils.logging import Logger

CONFIG_PATH_ENV = "BIGMED_SERVER_CONFIG"


@asynccontextmanager
async def lifespan(self: Server) -> AsyncGenerator[None, None]:
    import toml

    maybe_path = os.environ.get(CONFIG_PATH_ENV)
    if not maybe_path:
        msg = f"Please, provide {CONFIG_PATH_ENV} environmental variable"
        Logger.error(msg)
        raise RuntimeError(msg)

    path = Path(maybe_path)
    if path.is_dir():
        msg = f"Could not load server config: {path} is a directory"
        Logger.error(msg)
        raise IsADirectoryError(msg)
    elif not path.exists():
        msg = f"Could not load server config: {path} does not exist"
        Logger.error(msg)
        raise FileNotFoundError(msg)

    with path.open() as file:
        config = Cassandra.model_validate(toml.load(file))

    Logger.info("Configuring keyspace names")
    Medicine.__keyspace__ = config.keyspace  # pyright: ignore[reportAttributeAccessIssue]
    Reservation.__keyspace__ = config.keyspace  # pyright: ignore[reportAttributeAccessIssue]

    Logger.info(f"Connecting to {config.points}")
    with (
        Cluster(config.points) as cluster,
        cluster.connect(config.keyspace) as session,
    ):
        _ = register_connection(str(session), session=session)
        set_default_connection(str(session))
        self.session = session

        Logger.info("Preparing statements")
        columns = Reservation._columns  # pyright: ignore[reportAttributeAccessIssue]
        _ = session.prepare
        statements = Statements(
            medicine_conditional_update=_(
                f"UPDATE {Medicine.__name__.lower()} "
                "SET count = ? WHERE name = ? if count = ?"
            ),
            medicine_select=_(
                f"SELECT * FROM {Medicine.__name__.lower()} WHERE name = ?"
            ),
            medicine_select_count=_(
                f"SELECT count FROM {Medicine.__name__.lower()} WHERE name = ?"
            ),
            reservation_select=_(
                "SELECT account_name, medicine as name, count FROM "
                f"{Reservation.__name__.lower()} WHERE reservation_id = ?"
            ),
            reservation_select_account=_(
                "SELECT reservation_id, account_name, medicine as name, count "
                f"FROM {Reservation.__name__.lower()} WHERE "
                f"account_name = ? ALLOW FILTERING"
            ),
            reservation_select_all=_(
                "SELECT reservation_id, account_name, medicine as name, count "
                f"FROM {Reservation.__name__.lower()}"
            ),
            reservation_insert=_(
                "INSERT INTO {} ({}) VALUES ({});".format(
                    Reservation.__name__.lower(),
                    ", ".join(columns),
                    ", ".join("?" for _ in columns),
                )
            ),
        )
        self.statements = statements
        yield


@dataclass
class Statements:
    medicine_conditional_update: PreparedStatement
    medicine_select: PreparedStatement
    medicine_select_count: PreparedStatement
    reservation_select: PreparedStatement
    reservation_select_account: PreparedStatement
    reservation_select_all: PreparedStatement
    reservation_insert: PreparedStatement


class Server(FastAPI):
    def __init__(self, *args, **kwargs) -> None:
        _ = kwargs.setdefault("lifespan", lifespan)
        self.session: Session | None = None
        self.statements: Statements | None = None

        super().__init__(*args, **kwargs)


app = Server()


def session_and_statements() -> tuple[Session, Statements]:
    session = app.session
    statements = app.statements
    assert session
    assert statements
    return session, statements


@app.post("/reserve")
def reserve(request: Request, item: MedicineReservations) -> ResponseItem:
    # For each product
    # * verify whether count is ok
    # * decrease the count under the condition the count hasn't changed
    # * create new reservation
    session, statements = session_and_statements()

    current_counts = []
    for medicine in item.entries:
        current_counts.append(
            session.execute(
                statements.medicine_select_count.bind((medicine.name,))
            ).one()
        )

    # Subtract counts
    # Note: Batch with conditions cannot span multiple tables
    # therefore it is done in two stages
    medicine_and_counts = list(zip(item.entries, current_counts))
    for i, (medicine, current_count) in enumerate(medicine_and_counts):
        # Verify count
        current_count = (current_count or {}).get("count")
        if current_count is None:
            msg = f"Medicine {medicine.name} does not exist"
            Logger.debug(msg)
            return ResponseItem(
                msg=msg,
                type=ResponseType.ERROR,
            )

        # Compare count
        if medicine.count > current_count:
            msg = (
                f"Cannot reserve '{medicine.name}': requested "
                f"{medicine.count} units while there are only "
                f"{current_count}"
            )
            Logger.debug(msg)
            return ResponseItem(msg=msg, type=ResponseType.ERROR)

        # Execute
        try:
            session.execute(
                statements.medicine_conditional_update.bind((
                    current_count - medicine.count,
                    medicine.name,
                    current_count,
                ))
            )
        except Exception as ex:
            # Handle conflict: restore up to i-th medicine
            log_exception(ex)
            msg = "An exception occurred"
            return ResponseItem(type=ResponseType.EXCEPTION, msg=msg)

    reservation_id = uuid.uuid4()
    for medicine, current_count in zip(item.entries, current_counts):
        session.execute(
            statements.reservation_insert.bind((
                reservation_id,
                uuid.uuid4(),
                item.account_name,
                medicine.name,
                medicine.count,
            ))
        )

    msg = f"Reserved successfully: {reservation_id}."
    Logger.debug(msg)
    return ResponseItem(msg=msg, type=ResponseType.INFO)


@app.post("/update")
def update(request: Request, item: UpdateReservation) -> ResponseItem:
    # For each product
    # * verify whether new count is ok
    # * decrease the count under the condition the count hasn't changed
    # * remove old reservation
    # * create new reservation
    return ResponseItem(
        msg="Updated reservation successfully.",
        type=ResponseType.INFO,
    )


@app.get("/query")
def query(request: Request, id: str) -> ReservationResponse | ResponseItem:
    session, statements = session_and_statements()

    try:
        id_uuid = uuid.UUID(str(id))
    except ValueError:
        return ResponseItem(type=ResponseType.ERROR, msg="Invalid UUID")

    statement = statements.reservation_select.bind((id_uuid,))
    all = session.execute(statement).all()
    if not all:
        return ResponseItem(type=ResponseType.ERROR, msg="No such reservation")

    reservation_id = id
    account_name = all[0]["account_name"]
    return ReservationResponse(
        type=ResponseType.INFO,
        reservation_id=reservation_id,
        account_name=account_name,
        entries=[
            MedicineEntry(name=entry["name"], count=entry["count"])
            for entry in all
        ],
    )


def retrieve_reservations(
    session: Session, statement: PreparedStatement | BoundStatement
) -> ReservationsResponse | ResponseItem:
    all = session.execute(statement).all()
    if not all:
        msg = "No reservations found"
        return ResponseItem(type=ResponseType.ERROR, msg=msg)

    reservations = []
    getter = operator.itemgetter("reservation_id")
    for reservation_id, entries in itertools.groupby(all, getter):
        entries = list(entries)
        account_name = entries[0]["account_name"]
        reservation = ReservationEntryItem(
            reservation_id=str(reservation_id),
            account_name=account_name,
            entries=[
                MedicineEntry(name=entry["name"], count=entry["count"])
                for entry in entries
            ],
        )
        reservations.append(reservation)

    return ReservationsResponse(
        type=ResponseType.INFO,
        reservations=reservations,
    )


@app.get("/query-account")
def query_account(
    request: Request, name: str
) -> ReservationsResponse | ResponseItem:
    session, statements = session_and_statements()
    statement = statements.reservation_select_account.bind((name,))
    return retrieve_reservations(session, statement)


@app.get("/query-all")
def query_all() -> ReservationsResponse | ResponseItem:
    session, statements = session_and_statements()
    statement = statements.reservation_select_all
    return retrieve_reservations(session, statement)


@app.get("/medicine")
def medicine(request: Request, name: str) -> MedicineResponse | ResponseItem:
    session, statements = session_and_statements()
    query = statements.medicine_select.bind((name,))
    obj = session.execute(query).one()
    return MedicineResponse(medicine=dict(obj), type=ResponseType.INFO)


@app.get("/delete")
def delete() -> ResponseItem:
    assert app.session
    Logger.info("Cleaning the database")
    app.session.execute("DROP KEYSPACE medicines;")
    app.session.execute("DROP KEYSPACE reservations;")
    return ResponseItem(msg="Cleaned the database", type=ResponseType.INFO)


def log_exception(ex: Exception) -> None:
    trace = "\n".join(traceback.format_tb(ex.__traceback__))
    error_msg = f"Exception: {ex}\nStack trace:\n{trace}"
    Logger.error(error_msg)
