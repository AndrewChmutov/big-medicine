from __future__ import annotations

import asyncio
import itertools
import operator
import os
import traceback
import uuid
from collections.abc import AsyncGenerator, Iterable
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import toml
from cassandra import ConsistencyLevel, InvalidRequest
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
    DictResponse,
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


async def execute_async(
    session: Session,
    statement: str | PreparedStatement | BoundStatement,
) -> Any:
    loop = asyncio.get_running_loop()
    future = loop.create_future()

    def success_callback(result: Any) -> None:
        loop.call_soon_threadsafe(future.set_result, result)

    def error_callback(exc: Exception) -> None:
        Logger.error(f"Query failed: {exc}")
        loop.call_soon_threadsafe(future.set_exception, exc)

    cassandra_future = session.execute_async(statement)
    cassandra_future.add_callbacks(success_callback, error_callback)
    return await future


def init_empty(session: Session) -> None:
    maybe_path = os.environ.get(CONFIG_PATH_ENV)
    assert maybe_path
    path = Path(maybe_path)
    with path.open() as file:
        config = Cassandra.model_validate(toml.load(file))
    os.environ["CQLENG_ALLOW_SCHEMA_MANAGEMENT"] = "1"
    from cassandra.cqlengine.management import (
        create_keyspace_simple,
        sync_table,
    )

    keyspace_name = config.keyspace
    replication_factor = config.repl_factor
    _ = Logger.info
    _(f"Creating keyspace {keyspace_name} with {replication_factor=}")
    create_keyspace_simple(keyspace_name, replication_factor)
    sync_table(Medicine, keyspaces=[keyspace_name])
    sync_table(Reservation, keyspaces=[keyspace_name])
    session.set_keyspace(keyspace_name)


@asynccontextmanager
async def lifespan(self: Server) -> AsyncGenerator[None, None]:
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
        cluster.connect() as session,
    ):
        _ = register_connection(str(session), session=session)
        set_default_connection(str(session))
        self.session = session

        Logger.info("Preparing statements")
        columns = Reservation._columns  # pyright: ignore[reportAttributeAccessIssue]
        try:
            session.execute(f"USE {config.keyspace}")
        except InvalidRequest:
            init_empty(session)

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
            reservation_delete=_(
                f"DELETE FROM {Reservation.__name__.lower()} WHERE "
                "reservation_id = ?"
            ),
        )
        self.statements = statements
        Logger.info("The app is ready.")
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
    reservation_delete: PreparedStatement


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


async def get_current_counts(
    session: Session, statements: Statements, entries: Iterable[MedicineEntry]
) -> list[int | None]:
    futures = []
    for medicine in entries:
        statement = statements.medicine_select_count.bind((medicine.name,))
        statement.consistency_level = ConsistencyLevel.ALL
        futures.append(execute_async(session, statement))

    res = await asyncio.gather(*futures)
    return [(current_count or [{}])[0].get("count") for current_count in (res)]


def medicine_does_not_exist_response(medicine: MedicineEntry) -> ResponseItem:
    msg = f"Medicine {medicine.name} does not exist"
    Logger.debug(msg)
    return ResponseItem(
        msg=msg,
        type=ResponseType.ERROR,
    )


@app.post("/reserve")
async def reserve(
    request: Request, item: MedicineReservations
) -> ResponseItem:
    session, statements = session_and_statements()

    _ = get_current_counts
    current_counts = await _(session, statements, item.entries)
    medicine_and_counts = list(zip(item.entries, current_counts))
    for i, (medicine, current_count) in enumerate(medicine_and_counts):
        if current_count is None:
            return medicine_does_not_exist_response(medicine)

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
            statement = statements.medicine_conditional_update.bind((
                current_count - medicine.count,
                medicine.name,
                current_count,
            ))
            statement.consistency_level = ConsistencyLevel.ALL
            session.execute(statement)
        except Exception as ex:
            # Handle conflict: restore up to i-th medicine
            log_exception(ex)
            msg = "An exception occurred"
            return ResponseItem(type=ResponseType.EXCEPTION, msg=msg)

    reservation_id = uuid.uuid4()
    for medicine, current_count in zip(item.entries, current_counts):
        statement = statements.reservation_insert.bind((
            reservation_id,
            uuid.uuid4(),
            item.account_name,
            medicine.name,
            medicine.count,
        ))
        statement.consistency_level = ConsistencyLevel.ALL
        session.execute(statement)

    msg = f"Reserved successfully: {reservation_id}"
    Logger.debug(msg)
    return ResponseItem(msg=msg, type=ResponseType.INFO)


async def retrieve_single_reservation(
    session: Session, statements: Statements, id: str
) -> ReservationEntryItem | ResponseItem:
    try:
        id_uuid = uuid.UUID(str(id))
    except ValueError:
        return ResponseItem(type=ResponseType.ERROR, msg="Invalid UUID")

    statement = statements.reservation_select.bind((id_uuid,))
    all = await execute_async(session, statement)
    if not all:
        return ResponseItem(type=ResponseType.ERROR, msg="No such reservation")

    account_name = all[0]["account_name"]
    return ReservationEntryItem(
        id=id,
        account_name=account_name,
        entries=[
            MedicineEntry(name=entry["name"], count=entry["count"])
            for entry in all
        ],
    )


@app.post("/update")
async def update(request: Request, item: UpdateReservation) -> ResponseItem:
    session, statements = session_and_statements()

    match await retrieve_single_reservation(session, statements, item.id):
        case ReservationEntryItem() as reservation:
            pass
        case ResponseItem() as response:
            return response

    _ = get_current_counts
    current_counts = await _(session, statements, item.entries)
    current_reserved = {e.name: e.count for e in reservation.entries}
    medicine_and_counts = list(zip(item.entries, current_counts))
    for i, (medicine, current_count) in enumerate(medicine_and_counts):
        if current_count is None:
            return medicine_does_not_exist_response(medicine)

        # Compare count
        limit = current_count + current_reserved.get(medicine.name, 0)
        if medicine.count > limit:
            msg = (
                f"Cannot reserve '{medicine.name}': requested "
                f"{medicine.count} units while there are only "
                f"{limit}"
            )
            Logger.debug(msg)
            return ResponseItem(msg=msg, type=ResponseType.ERROR)

        # Execute
        try:
            session.execute(
                statements.medicine_conditional_update.bind((
                    limit - medicine.count,
                    medicine.name,
                    current_count,
                ))
            )
        except Exception as ex:
            # Handle conflict: restore up to i-th medicine
            log_exception(ex)
            msg = "An exception occurred"
            return ResponseItem(type=ResponseType.EXCEPTION, msg=msg)

    # Potential rollback in case of an error
    session.execute(
        statements.reservation_delete.bind((uuid.UUID(reservation.id),))
    )

    reservation_id = uuid.UUID(reservation.id)
    account_name = reservation.account_name
    for medicine, current_count in zip(item.entries, current_counts):
        session.execute(
            statements.reservation_insert.bind((
                reservation_id,
                uuid.uuid4(),
                account_name,
                medicine.name,
                medicine.count,
            ))
        )

    msg = f"Update successfully: {reservation_id}"
    Logger.debug(msg)
    return ResponseItem(msg=msg, type=ResponseType.INFO)


@app.get("/query")
async def query(
    request: Request, id: str
) -> ReservationResponse | ResponseItem:
    session, statements = session_and_statements()
    match await retrieve_single_reservation(session, statements, id):
        case ReservationEntryItem() as item:
            return ReservationResponse(
                type=ResponseType.INFO,
                id=item.id,
                account_name=item.account_name,
                entries=item.entries,
            )
        case ResponseItem() as response:
            return response


async def retrieve_reservations(
    session: Session, statement: PreparedStatement | BoundStatement
) -> list[ReservationEntryItem]:
    all = await execute_async(session, statement)

    getter = operator.itemgetter("reservation_id")
    reservations = []
    for reservation_id, entries in itertools.groupby(all, getter):
        entries = list(entries)
        account_name = entries[0]["account_name"]
        reservations.append(
            ReservationEntryItem(
                id=str(reservation_id),
                account_name=account_name,
                entries=[
                    MedicineEntry(name=entry["name"], count=entry["count"])
                    for entry in entries
                ],
            )
        )

    return reservations


async def retrieve_reservations_response(
    session: Session, statement: PreparedStatement | BoundStatement
) -> ReservationsResponse | ResponseItem:
    reservations = await retrieve_reservations(session, statement)
    if not reservations:
        msg = "No reservations found"
        return ResponseItem(type=ResponseType.ERROR, msg=msg)

    return ReservationsResponse(
        type=ResponseType.INFO,
        reservations=reservations,
    )


@app.get("/query-account")
async def query_account(
    request: Request, name: str
) -> ReservationsResponse | ResponseItem:
    session, statements = session_and_statements()
    statement = statements.reservation_select_account.bind((name,))
    return await retrieve_reservations_response(session, statement)


@app.get("/query-all")
async def query_all() -> ReservationsResponse | ResponseItem:
    session, statements = session_and_statements()
    statement = statements.reservation_select_all
    return await retrieve_reservations_response(session, statement)


@app.get("/medicine")
def medicine(request: Request, name: str) -> MedicineResponse | ResponseItem:
    session, statements = session_and_statements()
    query = statements.medicine_select.bind((name,))
    obj = session.execute(query).one()
    return MedicineResponse(medicine=dict(obj), type=ResponseType.INFO)


@app.get("/clean")
async def clean() -> ResponseItem:
    assert app.session
    Logger.info("Cleaning the database")
    await execute_async(app.session, "DROP KEYSPACE medicines;")
    init_empty(app.session)
    return ResponseItem(msg="Cleaned the database", type=ResponseType.INFO)


@app.get("/direct")
async def direct(request: Request, query: str) -> DictResponse:
    assert app.session
    statement = app.session.prepare(query).bind(())
    statement.consistency_level = ConsistencyLevel.ALL
    result = app.session.execute(statement)
    result = list(result)
    return DictResponse(
        msg="Performed request successfully.",
        type=ResponseType.INFO,
        content=result,
    )


def log_exception(ex: Exception) -> None:
    trace = "\n".join(traceback.format_tb(ex.__traceback__))
    error_msg = f"Exception: {ex}\nStack trace:\n{trace}"
    Logger.error(error_msg)
