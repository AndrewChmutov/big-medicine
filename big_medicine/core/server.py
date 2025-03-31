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
    substitute0 = columns.Text()
    substitute1 = columns.Text()
    substitute2 = columns.Text()
    substitute3 = columns.Text()
    substitute4 = columns.Text()
    side_effect0 = columns.Text()
    side_effect1 = columns.Text()
    side_effect2 = columns.Text()
    side_effect3 = columns.Text()
    side_effect4 = columns.Text()
    side_effect5 = columns.Text()
    side_effect6 = columns.Text()
    side_effect7 = columns.Text()
    side_effect8 = columns.Text()
    side_effect9 = columns.Text()
    side_effect10 = columns.Text()
    side_effect11 = columns.Text()
    side_effect12 = columns.Text()
    side_effect13 = columns.Text()
    side_effect14 = columns.Text()
    side_effect15 = columns.Text()
    side_effect16 = columns.Text()
    side_effect17 = columns.Text()
    side_effect18 = columns.Text()
    side_effect19 = columns.Text()
    side_effect20 = columns.Text()
    side_effect21 = columns.Text()
    side_effect22 = columns.Text()
    side_effect23 = columns.Text()
    side_effect24 = columns.Text()
    side_effect25 = columns.Text()
    side_effect26 = columns.Text()
    side_effect27 = columns.Text()
    side_effect28 = columns.Text()
    side_effect29 = columns.Text()
    side_effect30 = columns.Text()
    side_effect31 = columns.Text()
    side_effect32 = columns.Text()
    side_effect33 = columns.Text()
    side_effect34 = columns.Text()
    side_effect35 = columns.Text()
    side_effect36 = columns.Text()
    side_effect37 = columns.Text()
    side_effect38 = columns.Text()
    side_effect39 = columns.Text()
    side_effect40 = columns.Text()
    side_effect41 = columns.Text()
    use0 = columns.Text()
    use1 = columns.Text()
    use2 = columns.Text()
    use3 = columns.Text()
    use4 = columns.Text()
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
