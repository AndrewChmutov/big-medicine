import inspect
import logging
import os
import tempfile
from functools import partial, wraps
from pathlib import Path
from typing import Annotated, Callable, Self

from pydantic_typer import Typer as PydanticTyper
from typer import Argument, Option

from big_medicine.core.client.model import (
    Account,
    Cassandra,
    ClientNetwork,
    MedicineReservation,
    ServerNetwork,
)
from big_medicine.core.client.request import (
    AccountQuery,
    AllQuery,
    ReservationQuery,
    Reserve,
    Update,
)
from big_medicine.utils.logging import Logger
from big_medicine.utils.processing import prepare


class MedicineReservationCLI(MedicineReservation):
    @classmethod
    def parse(cls, value: str) -> Self:
        medicine, count = value.split(",")
        return cls(medicine=medicine, count=int(count))


# Custom arguments
medicine_argument = Argument(parser=MedicineReservationCLI.parse)
source_dataset = Argument(
    exists=True,
    file_okay=True,
    dir_okay=False,
    show_default=False,
    help="Path to the source dataset",
)
target_dataset = Argument(
    file_okay=True,
    dir_okay=False,
    show_default=False,
    help="Path to the target dataset (source dataset is used by default)",
)


# https://github.com/fastapi/typer/issues/88#issuecomment-1732469681
class AsyncTyper(PydanticTyper):
    @staticmethod
    def maybe_run_async(decorator: Callable, f: Callable) -> Callable:
        if inspect.iscoroutinefunction(f):
            import asyncio

            @wraps(f)
            def runner(*args, **kwargs):  # noqa: ANN202
                return asyncio.run(f(*args, **kwargs))

            decorator(runner)
        else:
            decorator(f)
        return f

    def callback(self, *args, **kwargs) -> Callable:
        decorator = super().callback(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)

    def command(self, *args, **kwargs) -> Callable:
        decorator = super().command(*args, **kwargs)
        return partial(self.maybe_run_async, decorator)


app = AsyncTyper(
    context_settings={"help_option_names": ["-h", "--help"]},
    add_completion=False,
)


# Commands
@app.command()
async def reserve(
    medicines: Annotated[list[MedicineReservationCLI], medicine_argument],
    account: Account,
    network: ClientNetwork,
) -> None:
    """Reserves medicines."""
    from big_medicine.core.client.core import Client

    async with Client(network, account) as client:
        await client.execute(Reserve(medicines))


@app.command()
async def update(
    id: Annotated[str, Argument(help="ID of the reservation")],
    medicines: Annotated[list[MedicineReservationCLI], medicine_argument],
    network: ClientNetwork,
) -> None:
    """Updates reservation."""
    from big_medicine.core.client.core import Client

    async with Client(network) as client:
        await client.execute(Update(id, medicines))


@app.command()
async def query_account(
    account: Account,
    network: ClientNetwork,
) -> None:
    """Retrieves a specific reservation."""
    from big_medicine.core.client.core import Client

    async with Client(network) as client:
        await client.execute(AccountQuery(account.name))


@app.command()
async def query_all(
    network: ClientNetwork,
) -> None:
    """Retrieves all reservations in the system."""
    from big_medicine.core.client.core import Client

    async with Client(network) as client:
        await client.execute(AllQuery())


@app.command()
async def query_by_id(
    id: str,
    network: ClientNetwork,
) -> None:
    """Retrieves a single reservation by ID."""
    from big_medicine.core.client.core import Client

    async with Client(network) as client:
        await client.execute(ReservationQuery(id))


@app.command()
def prepare_dataset(
    source: Annotated[Path, source_dataset],
    target: Annotated[Path | None, target_dataset] = None,
    min_value: Annotated[
        int,
        Option("--min", min=0),
    ] = 0,
    max_value: Annotated[int, Option("--max", min=0)] = 1000,
    take: Annotated[int, Option(min=0)] = 1000,
) -> None:
    """Adds column representing the number of present medicines."""
    if not target:
        target = source
        Logger.info(f"Reusing 'source' for 'target': {target}")

    import pandas as pd

    try:
        data = pd.read_csv(source)
    except pd.errors.ParserError:
        Logger.error("Could not parse a csv.")
        return

    data = prepare(data, min_value, max_value, take)
    data.to_csv(target, index=True)


@app.command()
def serve(
    cassandra: Cassandra,
    network: ServerNetwork,
) -> None:
    """Creates a FastAPI server for request handling."""
    import toml
    import uvicorn

    from big_medicine.core.server.core import CONFIG_PATH_ENV

    with tempfile.NamedTemporaryFile() as tfile:
        with open(tfile.name, "w") as file:
            toml.dump(cassandra.model_dump(), file)

        os.environ[CONFIG_PATH_ENV] = file.name

        Logger.info("Starting an app...")
        uvicorn.run(
            "big_medicine.core.server.core:app",
            host=network.ip,
            port=network.port,
            log_level=logging.INFO,
            log_config=None,
            reload=True,
        )


@app.command()
def dataset_to_cassandra(
    prepared_dataset: Annotated[Path, source_dataset],
    cassandra: Cassandra,
) -> None:
    import pandas as pd
    from cassandra.cluster import Cluster
    from cassandra.cqlengine.connection import (
        register_connection,
        set_default_connection,
    )

    from big_medicine.utils.db import upload

    try:
        Logger.info(f"Reading the dataset {prepared_dataset}")
        data = pd.read_csv(prepared_dataset, low_memory=False, index_col="id")
    except pd.errors.ParserError:
        Logger.error("Could not parse a csv.")
        return

    Logger.info(f"Connecting to {cassandra.points}")
    with Cluster(cassandra.points) as cluster, cluster.connect() as session:
        _ = register_connection(str(session), session=session)
        set_default_connection(str(session))

        upload(data, cassandra.keyspace, cassandra.repl_factor)
