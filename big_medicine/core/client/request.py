from __future__ import annotations

import sys
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import TYPE_CHECKING, Any

from big_medicine.core.client.model import MedicineReservation
from big_medicine.utils.logging import Logger

if TYPE_CHECKING:
    from aiohttp import ClientResponse, ClientSession

from big_medicine.core.server.message import (
    MedicineEntry,
    MedicineReservations,
    UpdateReservation,
)


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
            await self.handle_response(response)

    def params(self) -> dict[str, Any]:
        return {}

    async def handle_response(self, response: ClientResponse) -> None:
        content = await response.json()
        Logger.info(f"{content}")


class PostRequest(Request):
    async def execute(self, session: ClientSession, base_url: str) -> None:
        async with session.post(
            self.url(base_url), json=self.json()
        ) as response:
            await self.handle_response(response)

    @abstractmethod
    def json(self) -> dict[str, Any]: ...

    async def handle_response(self, response: ClientResponse) -> None:
        content = await response.json()
        Logger.info(f"{content}")


class Reserve(PostRequest):
    def __init__(
        self, account_name: str, entries: Iterable[MedicineReservation]
    ) -> None:
        self.entries = entries
        self.account_name = account_name

    def model_entries(self) -> list[MedicineEntry]:
        entries = list(self.entries)
        if len(set(e.medicine for e in self.entries)) != len(entries):
            Logger.error("Use of duplicated medicines.")
            sys.exit(1)
        return [MedicineEntry(name=e.medicine, count=e.count) for e in entries]

    def json(self) -> dict[str, Any]:
        return MedicineReservations(
            account_name=self.account_name, entries=self.model_entries()
        ).model_dump()

    @staticmethod
    def route() -> str:
        return "/reserve"


class Update(Reserve):
    def __init__(
        self,
        id: str,
        account_name: str,
        entries: Iterable[MedicineReservation],
    ) -> None:
        super().__init__(account_name, entries)
        self.id = id

    def json(self) -> dict[str, Any]:
        return UpdateReservation(
            id=self.id, entries=self.model_entries()
        ).model_dump()

    @staticmethod
    def route() -> str:
        return "/update"


class Query(GetRequest):
    pass


class Clean(GetRequest):
    @staticmethod
    def route() -> str:
        return "/clean"


class ReservationQuery(Query):
    def __init__(self, id: str) -> None:
        self.id = id

    def params(self) -> dict[str, Any]:
        return {"id": self.id}

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

    def params(self) -> dict[str, Any]:
        return {"name": self.name}

    @staticmethod
    def route() -> str:
        return "/medicine"


class DirectRequest(GetRequest):
    def __init__(self, query: str) -> None:
        self.query = query

    def params(self) -> dict[str, Any]:
        return {"query": self.query}

    @staticmethod
    def route() -> str:
        return "/direct"
