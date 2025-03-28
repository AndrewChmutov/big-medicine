import inspect
from functools import partial, wraps
from pathlib import Path
from typing import Annotated, Callable, Self

from pydantic_typer import Typer as PydanticTyper
from typer import Argument, Option

from big_medicine.core.client import (
    AccountQuery,
    Client,
    EntireQuery,
    SpecificQuery,
)
from big_medicine.core.model import (
    Account,
    Cassandra,
    ClientNetwork,
    MedicineReservation,
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
    async with Client(network, account) as client:
        client.reserve(medicines)


@app.command()
async def update(
    id: Annotated[str, Argument(help="ID of the reservation")],
    medicines: Annotated[list[MedicineReservationCLI], medicine_argument],
    network: ClientNetwork,
) -> None:
    """Updates reservation."""
    async with Client(network) as client:
        client.update(id, medicines)


@app.command()
async def query(
    id: Annotated[str, Argument(help="ID of the reservation")],
    account: Account,
    network: ClientNetwork,
) -> None:
    """Retrieves account reservations."""
    client = Client(network, account)
    client.query(AccountQuery(id=id))


@app.command()
async def query_all(
    network: ClientNetwork,
) -> None:
    """Retrieves all reservations in the system."""
    client = Client(network)
    client.query(EntireQuery())


@app.command()
async def query_by_id(
    id: str,
    network: ClientNetwork,
    account: Account,
) -> None:
    """Retrieves a single reservation by ID."""
    client = Client(network, account)
    client.query(SpecificQuery(id=id))


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
    data.to_csv(target)


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
        data = pd.read_csv(prepared_dataset, low_memory=False)
    except pd.errors.ParserError:
        Logger.error("Could not parse a csv.")
        return

    Logger.info(f"Connecting to {cassandra.points}")
    with Cluster(cassandra.points) as cluster, cluster.connect() as session:
        _ = register_connection(str(session), session=session)
        set_default_connection(str(session))

        upload(data, cassandra.keyspace, cassandra.repl_factor)
