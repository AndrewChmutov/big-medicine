from enum import Enum

from pydantic import BaseModel


class MedicineEntry(BaseModel):
    name: str
    count: int


class MedicineReservations(BaseModel):
    entries: list[MedicineEntry]
    account_name: str


class UpdateReservation(BaseModel):
    id: str
    entries: list[MedicineEntry]


class ResponseType(str, Enum):
    INFO = "info"
    ERROR = "error"


class ResponseItem(BaseModel):
    type: ResponseType
    msg: str = "-"


class ReservationEntryItem(BaseModel):
    reservation_id: int
    medicine: str
    count: str


class ReservationResponse(ResponseItem):
    reservation: ReservationEntryItem | None


class ReservationsResponse(ResponseItem):
    reservations: list[ReservationEntryItem]


class MedicineResponse(ResponseItem):
    medicine: dict | None
