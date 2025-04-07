import asyncio
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio

from big_medicine.core.client.core import Client
from big_medicine.core.client.model import Account, ClientNetwork
from big_medicine.core.client.request import AccountQuery


@pytest_asyncio.fixture
async def client() -> AsyncIterator[Client]:
    async with Client(ClientNetwork(), Account()) as client:
        yield client


@pytest.mark.asyncio
async def test_latency(client: Client) -> None:
    assert client._account
    query = AccountQuery(client._account.name)
    await asyncio.gather(*[client.execute(query) for _ in range(1000)])
