from __future__ import annotations

import os
import traceback
import uuid
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from cassandra.cluster import Session
from cassandra.cqlengine.connection import (
    Cluster,
    register_connection,
    set_default_connection,
)
from cassandra.query import BatchStatement, BatchType, PreparedStatement
from fastapi import FastAPI, Request

from big_medicine.core.client.model import Cassandra
from big_medicine.core.server.message import (
    MedicineReservations,
    MedicineResponse,
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
        self.st_reserve = session.prepare(
            "INSERT INTO {} ({}) VALUES ({});".format(
                Reservation.__name__.lower(),
                ", ".join(columns),
                ", ".join("?" for _ in columns),
            )
        )
        self.st_decrease_medicine = session.prepare(
            f"UPDATE {Medicine.__name__.lower()} "
            "SET count = ? WHERE name = ? if count = ?"
        )

        self.st_get_medicine = session.prepare(
            f"SELECT * FROM {Medicine.__name__.lower()} WHERE name = ?"
        )

        self.st_get_current_count = session.prepare(
            f"SELECT count FROM {Medicine.__name__.lower()} WHERE name = ?"
        )

        yield


class Server(FastAPI):
    def __init__(self, *args, **kwargs) -> None:
        _ = kwargs.setdefault("lifespan", lifespan)
        self.session: Session | None = None
        self.st_reserve: PreparedStatement | None = None
        self.st_decrease_medicine: PreparedStatement | None = None
        self.st_get_medicine: PreparedStatement | None = None
        self.query_account_statement: PreparedStatement | None = None
        self.st_get_current_count: PreparedStatement | None = None

        super().__init__(*args, **kwargs)


app = Server()


@app.post("/reserve")
def reserve(request: Request, item: MedicineReservations) -> ResponseItem:
    # For each product
    # * verify whether count is ok
    # * decrease the count under the condition the count hasn't changed
    # * create new reservation
    session = app.session
    assert session

    current_counts = []
    for medicine in item.entries:
        current_counts.append(
            session.execute(
                app.st_get_current_count.bind((medicine.name,))
            ).one()
        )

    # Subtract counts
    # Note: Batch with conditions cannot span multiple tables
    # therefore it is done in two stages
    batch = BatchStatement()
    for medicine, current_count in zip(item.entries, current_counts):
        current_count = (current_count or {}).get("count")
        if current_count is None:
            msg = f"Medicine {medicine.name} does not exist"
            Logger.debug(msg)
            return ResponseItem(
                msg=msg,
                type=ResponseType.ERROR,
            )
        if medicine.count > current_count:
            msg = (
                f"Cannot reserve '{medicine.name}': requested "
                f"{medicine.count} units while there are only "
                f"{current_count}"
            )
            Logger.debug(msg)
            return ResponseItem(msg=msg, type=ResponseType.ERROR)

        batch.add(
            app.st_decrease_medicine.bind((
                current_count - medicine.count,
                medicine.name,
                current_count,
            ))
        )

    if not session.execute(batch)[0]["[applied]"]:
        msg = "Couldn't find the meds for the given reservation"
        Logger.debug(msg)
        return ResponseItem(msg=msg, type=ResponseType.ERROR)

    batch = BatchStatement(batch_type=BatchType.UNLOGGED)
    reservation_id = uuid.uuid4()
    for medicine, current_count in zip(item.entries, current_counts):
        id = uuid.uuid4()
        batch.add(
            app.st_reserve.bind((
                id,
                reservation_id,
                item.account_name,
                medicine.name,
                medicine.count,
            ))
        )
    session.execute(batch)

    return ResponseItem(msg="Reserved successfully.", type=ResponseType.INFO)


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
def query(request: Request, id: int) -> ReservationResponse:
    # Filter by reservation id and group by reservation id
    return ReservationResponse(
        type=ResponseType.INFO,
        reservation=None,
    )


@app.get("/query-account")
def query_account(request: Request, name: str) -> ReservationsResponse:
    # Filter by account and group by reservation id
    # Collect
    return ReservationsResponse(
        type=ResponseType.INFO,
        reservations=[],
    )


@app.get("/query-all")
def query_all() -> ReservationsResponse:
    # Group by reservation id
    # Collect
    return ReservationsResponse(
        type=ResponseType.INFO,
        reservations=[],
    )


@app.get("/medicine")
def medicine(request: Request, name: str) -> MedicineResponse:
    assert app.session
    assert app.medicine_statement
    try:
        query = app.medicine_statement.bind(name)
        obj = app.session.execute(query).one()
        return MedicineResponse(medicine=dict(obj), type=ResponseType.INFO)
    except Exception as ex:
        log_exception(ex)
        return MedicineResponse(medicine=None, type=ResponseType.INFO)


@app.get("/delete")
def delete() -> ResponseItem:
    assert app.session
    Logger.info("Cleaning the database")
    app.session.execute("DROP KEYSPACE medicines;")
    return ResponseItem(msg="Cleaned the database", type=ResponseType.INFO)


def log_exception(ex: Exception) -> None:
    trace = "\n".join(traceback.format_tb(ex.__traceback__))
    error_msg = f"Exception: {ex}\nStack trace:\n{trace}"
    Logger.error(error_msg)
