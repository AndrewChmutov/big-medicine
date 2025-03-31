from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from pathlib import Path

from cassandra.cluster import Session
from cassandra.cqlengine import columns
from cassandra.cqlengine.connection import (
    Cluster,
    register_connection,
    set_default_connection,
)
from cassandra.cqlengine.models import Model
from fastapi import FastAPI
from fastapi.responses import JSONResponse

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


class Reservation(Model):
    id = columns.Integer(primary_key=True)
    account_name = columns.Text()
    medicine = columns.Text()
    count = columns.Text()


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


@app.get("/query")
def query() -> JSONResponse:
    for med in Medicine.objects().all():
        print(med.name)
    return JSONResponse({"kek": "hello"})


@app.get("/delete")
def delete() -> JSONResponse:
    assert app.session
    app.session.execute(f"DROP KEYSPACE {Medicine.__keyspace__};")
    # app.session.execute(f"TRUNCATE {Medicine.__keyspace__}.Medicine;")
    return JSONResponse({"kek": "hello"})
