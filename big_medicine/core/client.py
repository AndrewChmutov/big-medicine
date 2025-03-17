from collections.abc import Iterable
from dataclasses import dataclass

from big_medicine.core.model import Account, ClientNetwork, MedicineReservation
from big_medicine.utils.logging import Logger


class Query:
    pass


@dataclass
class AccountQuery(Query):
    id: str
    account: Account


@dataclass
class EntireQuery(Query):
    pass


@dataclass
class SpecificQuery(Query):
    id: str


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

    @Logger.func()
    def reserve(
        self,
        reservations: Iterable[MedicineReservation],
    ) -> str: ...

    @Logger.func()
    def update(
        self,
        id: str,
        reservations: Iterable[MedicineReservation],
    ) -> None: ...

    @Logger.func()
    def query(self, query: Query) -> None:
        pass

    def __repr__(self) -> str:
        network = self._network
        account = self._account
        return f"Client({network=}, {account=})"
