import asyncio
import logging
import random
import traceback
from collections.abc import AsyncIterator
from multiprocessing import Pipe, Process
from typing import ClassVar

import pytest
import pytest_asyncio

from big_medicine.core.client.core import Client
from big_medicine.core.client.model import Account, ClientNetwork
from big_medicine.core.client.request import (
    AccountQuery,
    AllQuery,
    MedicineQuery,
    Request,
)
from big_medicine.utils.logging import Logger


@pytest_asyncio.fixture
async def client() -> AsyncIterator[Client]:
    async with Client(ClientNetwork(), Account()) as client:
        yield client


@pytest.mark.asyncio
@pytest.mark.parametrize("n", [1, 10, 100, 1000])
async def test_latency(client: Client, n: int) -> None:
    assert client._account
    query = AccountQuery(client._account.name)
    await asyncio.gather(*[client.execute(query) for _ in range(n)])


class Request_:
    _types: ClassVar[list[type[Request]]] = []

    def __init_subclass__(cls) -> None:
        cls._types.append(cls)  # pyright: ignore[reportArgumentType]


class AllQuery_(AllQuery, Request_):
    def __init__(self, account_name: str) -> None:
        super().__init__()


class AccountQuery_(AccountQuery, Request_): ...


class MedicineQuery_(MedicineQuery, Request_):
    def __init__(self, account_name: str) -> None:
        super().__init__("allegra 120mg tablet")


class ProcessWithException(Process):
    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._pconn, self._cconn = Pipe()
        self._exception = None

    def run(self) -> None:
        try:
            super().run()
            self._cconn.send(None)
        except Exception as ex:
            trace = traceback.format_exc()
            error_msg = f"Exception: {ex}\nStack trace:\n{trace}"
            self._cconn.send(error_msg)
            raise

    @property
    def exception(self) -> str | None:
        if self._pconn.poll():
            self._exception = self._pconn.recv()
        assert isinstance(self._exception, (str, type(None)))
        return self._exception


async def async_process_random_queries(name: str, n_requests: int) -> None:
    query_types = random.choices(Request_._types, k=n_requests)
    queries = [cls(name) for cls in query_types]  # pyright: ignore[reportCallIssue]
    async with Client(ClientNetwork(), Account(name=name)) as client:
        futures = map(client.execute, queries)
        await asyncio.gather(*futures)


def process_random_queries(name: str, n_requests: int) -> None:
    Logger.setLevel(logging.WARNING)
    Logger.warning(f"Launching {name}")
    asyncio.run(async_process_random_queries(name, n_requests))


@pytest.mark.parametrize("n_requests", [100, 150])
@pytest.mark.parametrize("n_clients", [2, 3])
def test_multiple_clients(n_clients: int, n_requests: int) -> None:
    print()
    processes = [
        ProcessWithException(
            target=process_random_queries,
            name=(name := f"client-{i}"),
            args=(name, n_requests),
        )
        for i in range(n_clients)
    ]

    for process in processes:
        process.start()

    for process in processes:
        process.join()
        if tb := process.exception:
            pytest.fail(tb)
