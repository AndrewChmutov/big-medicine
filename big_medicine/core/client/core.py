from __future__ import annotations

from types import TracebackType
from typing import TYPE_CHECKING

from big_medicine.core.client.model import Account, ClientNetwork
from big_medicine.core.client.request import Request

if TYPE_CHECKING:
    from aiohttp import ClientSession


class Client:
    def __init__(
        self, network: ClientNetwork, account: Account | None = None
    ) -> None:
        """Instantiates Client.

        Args:
            network: Network configuration.
            account: Account configuration.
        """
        self._network = network
        self._account = account
        self._session: ClientSession | None = None

    async def __aenter__(self) -> "Client":
        from aiohttp import ClientSession

        self._session = await ClientSession().__aenter__()
        return self

    async def __aexit__(
        self,
        exc_type: type[Exception] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        assert self._session
        await self._session.__aexit__(exc_type, exc_val, exc_tb)

    async def execute(self, request: Request) -> None:
        assert self._session
        await request.execute(self._session, self.base_url)

    @property
    def base_url(self) -> str:
        assert self._network
        return f"http://{self._network.ip}:{self._network.port}"

    def __repr__(self) -> str:
        network = self._network
        account = self._account
        return f"Client({network=}, {account=})"
