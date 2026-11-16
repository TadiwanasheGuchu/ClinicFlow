import uuid
from datetime import date, datetime, time
from decimal import Decimal
from itertools import pairwise

from pydantic import Field, field_validator, model_validator

from app.shared.schemas import Schema


class ProviderCreate(Schema):
    membership_id: uuid.UUID
    display_name: str | None = Field(None, min_length=2, max_length=200)
    online_booking_enabled: bool = False


class ProviderUpdate(Schema):
    display_name: str | None = Field(None, min_length=2, max_length=200)
    booking_enabled: bool | None = None
    online_booking_enabled: bool | None = None

    @model_validator(mode="after")
    def _not_null(self) -> "ProviderUpdate":
        for name in self.model_fields_set:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class ProviderRead(Schema):
    id: uuid.UUID
    membership_id: uuid.UUID
    display_name: str
    profession: str
    specialty: str | None
    booking_enabled: bool
    online_booking_enabled: bool
    # False when registration is unverified or the licence has expired; such providers
    # cannot be booked even if booking is enabled.
    credentials_current: bool
    branch_ids: list[uuid.UUID]


class AvailabilityWindow(Schema):
    branch_id: uuid.UUID
    weekday: int = Field(ge=0, le=6, description="0 = Monday")
    start_time: time
    end_time: time
    effective_from: date | None = None
    effective_until: date | None = None

    @model_validator(mode="after")
    def _valid(self) -> "AvailabilityWindow":
        if self.start_time >= self.end_time:
            raise ValueError("Start time must be before end time.")
        if (
            self.effective_from
            and self.effective_until
            and self.effective_from > self.effective_until
        ):
            raise ValueError("effective_from must be on or before effective_until.")
        return self


class AvailabilityRead(AvailabilityWindow):
    id: uuid.UUID


class AvailabilityReplace(Schema):
    windows: list[AvailabilityWindow] = Field(max_length=100)

    @field_validator("windows")
    @classmethod
    def _no_overlap(cls, windows: list[AvailabilityWindow]) -> list[AvailabilityWindow]:
        # A provider cannot be in two places at once, whichever branch.
        by_day: dict[int, list[AvailabilityWindow]] = {}
        for w in windows:
            by_day.setdefault(w.weekday, []).append(w)
        for day, items in by_day.items():
            items.sort(key=lambda w: w.start_time)
            for a, b in pairwise(items):
                ranges_overlap = (
                    a.effective_until is None
                    or b.effective_from is None
                    or b.effective_from <= a.effective_until
                ) and (
                    b.effective_until is None
                    or a.effective_from is None
                    or a.effective_from <= b.effective_until
                )
                if b.start_time < a.end_time and ranges_overlap:
                    raise ValueError(f"Overlapping working hours on weekday {day}.")
        return windows


class UnavailabilityCreate(Schema):
    start_at: datetime
    end_at: datetime
    reason: str | None = Field(None, max_length=500)

    @model_validator(mode="after")
    def _valid(self) -> "UnavailabilityCreate":
        if self.start_at.tzinfo is None or self.end_at.tzinfo is None:
            raise ValueError("Times must include a timezone offset.")
        if self.start_at >= self.end_at:
            raise ValueError("Start must be before end.")
        return self


class UnavailabilityRead(Schema):
    id: uuid.UUID
    start_at: datetime
    end_at: datetime
    reason: str | None


class AppointmentTypeCreate(Schema):
    name: str = Field(min_length=2, max_length=100)
    description: str | None = Field(None, max_length=1000)
    duration_minutes: int = Field(ge=5, le=480)
    fee: Decimal = Field(ge=0, max_digits=12, decimal_places=2)
    booking_buffer_minutes: int = Field(0, ge=0, le=120)


class AppointmentTypeUpdate(Schema):
    name: str | None = Field(None, min_length=2, max_length=100)
    description: str | None = Field(None, max_length=1000)
    duration_minutes: int | None = Field(None, ge=5, le=480)
    fee: Decimal | None = Field(None, ge=0, max_digits=12, decimal_places=2)
    booking_buffer_minutes: int | None = Field(None, ge=0, le=120)
    is_active: bool | None = None

    @model_validator(mode="after")
    def _not_null(self) -> "AppointmentTypeUpdate":
        for name in self.model_fields_set - {"description"}:
            if getattr(self, name) is None:
                raise ValueError(f"{name} cannot be null.")
        return self


class AppointmentTypeRead(Schema):
    id: uuid.UUID
    name: str
    description: str | None
    duration_minutes: int
    fee: Decimal
    booking_buffer_minutes: int
    is_active: bool


class Slot(Schema):
    start_at: datetime
    end_at: datetime
