from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Iterable
from types import TracebackType
from typing import TYPE_CHECKING, Any, Self

from big_medicine.core.model import Account, ClientNetwork, MedicineReservation
from big_medicine.utils.logging import Logger

if TYPE_CHECKING:
    from aiohttp import ClientResponse, ClientSession

    from big_medicine.core.server import MedicineEntry


class Request(ABC):
    async def execute(self, session: ClientSession, base_url: str) -> None: ...

    @staticmethod
    @abstractmethod
    def route() -> str: ...

    @classmethod
    def url(cls, base_url: str) -> str:
        return base_url + cls.route()


class GetRequest(Request):
    async def execute(self, session: ClientSession, base_url: str) -> None:
        async with session.get(
            self.url(base_url), params=self.params()
        ) as response:
            self.handle_response(response)

    def params(self) -> dict[str, Any]:
        return {}

    def handle_response(self, response: ClientResponse) -> None:
        Logger.info(f"{response}")


class PostRequest(Request):
    async def execute(self, session: ClientSession, base_url: str) -> None:
        async with session.post(
            self.url(base_url), json=self.json()
        ) as response:
            self.handle_response(response)

    @abstractmethod
    def json(self) -> dict[str, Any]: ...

    def handle_response(self, response: ClientResponse) -> None:
        Logger.info(f"{response}")


class Reserve(PostRequest):
    def __init__(self, entries: Iterable[MedicineReservation]) -> None:
        self.entries = entries

    def model_entries(self) -> list[MedicineEntry]:
        from big_medicine.core.server import MedicineEntry

        return [
            MedicineEntry(name=e.medicine, count=e.count) for e in self.entries
        ]

    def json(self) -> dict[str, Any]:
        from big_medicine.core.server import (
            MedicineReservations,
        )

        return MedicineReservations(entries=self.model_entries()).model_dump()

    @staticmethod
    def route() -> str:
        return "/reserve"


class Update(Reserve):
    def __init__(
        self,
        id: str,
        entries: Iterable[MedicineReservation],
    ) -> None:
        super().__init__(entries)
        self.id = id

    def json(self) -> dict[str, Any]:
        from big_medicine.core.server import UpdateReservation

        return UpdateReservation(
            id=self.id, entries=self.model_entries()
        ).model_dump()

    @staticmethod
    def route() -> str:
        return "/update"


class Query(GetRequest):
    pass


class ReservationQuery(Query):
    def __init__(self, id: str) -> None:
        self.id = id

    @staticmethod
    def route() -> str:
        return "/query"


class AccountQuery(Query):
    def __init__(self, account: str) -> None:
        self.account = account

    def params(self) -> dict[str, Any]:
        return {"name": self.account}

    @staticmethod
    def route() -> str:
        return "/query-account"


class AllQuery(Query):
    @staticmethod
    def route() -> str:
        return "/query-all"


class MedicineQuery(Query):
    def __init__(self, name: str) -> None:
        self.name = name

    @staticmethod
    def route() -> str:
        return "/medicine"


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

    async def __aenter__(self) -> Self:
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
