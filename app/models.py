"""Strict request types for the HTTP API."""

import re
from datetime import date
from typing import Annotated

from pydantic import BaseModel, BeforeValidator, Field, StrictInt, StrictStr, model_validator

UInt64 = Annotated[StrictInt, Field(ge=0, le=2**64 - 1)]
UInt32 = Annotated[StrictInt, Field(ge=0, le=2**32 - 1)]
NonemptyString = Annotated[StrictStr, Field(min_length=1, pattern=r"\S")]


def parse_date(value: object) -> date:
    if not isinstance(value, str) or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value):
        raise ValueError("Expected YYYY-MM-DD")
    return date.fromisoformat(value)


ISODate = Annotated[date, BeforeValidator(parse_date)]


class UserPatch(BaseModel):
    fio: NonemptyString | None = None
    phone: NonemptyString | None = None

    @model_validator(mode="after")
    def check_fields(self) -> "UserPatch":
        if not self.model_fields_set:
            raise ValueError("At least one field is required")
        for field in ("fio", "phone"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f'invalid "{field}" field')
        return self


class ReadingCreate(BaseModel):
    user_id: UInt64
    gauge_id: UInt64
    tariff_id: UInt64
    reading_date: ISODate
    day_kw: UInt32
    night_kw: UInt32


class GaugeInstall(BaseModel):
    gauge_id: UInt64
