from __future__ import annotations

import os
import traceback
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from enum import Enum
from pathlib import Path

from cassandra.cluster import Session
from cassandra.cqlengine import columns
from cassandra.cqlengine.connection import (
    Cluster,
    register_connection,
    set_default_connection,
)
from cassandra.cqlengine.models import Model
from fastapi import FastAPI, Request
from pydantic import BaseModel

from big_medicine.core.model import Cassandra
from big_medicine.utils.logging import Logger


class Medicine(Model):
    name = columns.Text(primary_key=True)
    substitutes = columns.List(columns.Text())
    side_effects = columns.List(columns.Text())
    uses = columns.List(columns.Text())
    chemical_class = columns.Text()
    habit_forming = columns.Text()
    therapeutic_class = columns.Text()
    action_class = columns.Text()
    count = columns.Integer()


class ReservationEntry(Model):
    medicine = columns.Text(primary_key=True)
    reservation_id = columns.Integer(primary_key=True)
    count = columns.Text()


class Reservation(Model):
    id = columns.Integer(primary_key=True)
    account_name = columns.Text()


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
    ReservationEntry.__keyspace__ = config.keyspace  # pyright: ignore[reportAttributeAccessIssue]
    Reservation.__keyspace__ = config.keyspace  # pyright: ignore[reportAttributeAccessIssue]

    with Cluster(config.points) as cluster, cluster.connect() as session:
        _ = register_connection(str(session), session=session)
        set_default_connection(str(session))
        self.session = session
        yield


class Server(FastAPI):
    def __init__(self, *args, **kwargs) -> None:
        _ = kwargs.setdefault("lifespan", lifespan)
        self.session: Session | None = None
        super().__init__(*args, **kwargs)


app = Server()


class MedicineReservation(BaseModel):
    name: str
    count: int


class ResponseType(str, Enum):
    INFO = "info"
    ERROR = "error"


class ResponseItem(BaseModel):
    type: ResponseType
    msg: str = "-"


class ReservationEntryItem(BaseModel):
    reservation_id: int
    medicine: str
    count: str


class ReservationResponse(ResponseItem):
    reservation: ReservationEntryItem | None


class ReservationsResponse(ResponseItem):
    reservations: list[ReservationEntryItem]


class MedicineResponse(ResponseItem):
    medicine: dict | None


@app.post("/reserve")
def reserve(request: Request, item: MedicineReservation) -> ResponseItem:
    return ResponseItem(msg="Reserved successfully.", type=ResponseType.INFO)


@app.get("/update")
def update(request: Request, name: str) -> ResponseItem:
    return ResponseItem(
        msg=f"Updated reservation '{name}' successfully.",
        type=ResponseType.INFO,
    )


@app.get("/query")
def query(request: Request, id: int) -> ReservationResponse:
    return ReservationResponse(
        type=ResponseType.INFO,
        reservation=None,
    )


@app.get("/query-account")
def query_account(request: Request, name: str) -> ReservationsResponse:
    return ReservationsResponse(
        type=ResponseType.INFO,
        reservations=[],
    )


@app.get("/query-all")
def query_all() -> ReservationsResponse:
    return ReservationsResponse(
        type=ResponseType.INFO,
        reservations=[],
    )


@app.get("/medicine")
def medicine(request: Request, name: str) -> MedicineResponse:
    try:
        obj = Medicine.objects.allow_filtering().filter(name=name).get()
        return MedicineResponse(medicine=dict(obj), type=ResponseType.INFO)
    except Exception as ex:
        log_exception(ex)
        return MedicineResponse(medicine=None, type=ResponseType.INFO)


@app.get("/delete")
def delete() -> ResponseItem:
    assert app.session
    keyspace = Medicine.__keyspace__
    Logger.info(f"Removing keyspace {keyspace}")
    try:
        app.session.execute(f"DROP KEYSPACE {keyspace};")
        return ResponseItem(
            msg=f"Deleted the keyspace {keyspace}", type=ResponseType.INFO
        )
    except Exception as ex:
        log_exception(ex)
        return ResponseItem(msg="Database is empty", type=ResponseType.INFO)


def log_exception(ex: Exception) -> None:
    trace = "\n".join(traceback.format_tb(ex.__traceback__))
    error_msg = f"Exception: {ex}\nStack trace:\n{trace}"
    Logger.error(error_msg)
