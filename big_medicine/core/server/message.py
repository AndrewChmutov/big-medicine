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
    EXCEPTION = "exception"


class ResponseItem(BaseModel):
    type: ResponseType
    msg: str = "-"


class ReservationEntryItem(BaseModel):
    id: str
    account_name: str
    entries: list[MedicineEntry]


class ReservationResponse(ResponseItem, ReservationEntryItem): ...


class ReservationsResponse(ResponseItem):
    reservations: list[ReservationEntryItem]


class MedicineResponse(ResponseItem):
    medicine: dict


class DictResponse(ResponseItem):
    content: dict | list
