from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from unicodedata import normalize


class RecordError(ValueError):
    def __init__(self, field: str, reason: str):
        super().__init__(f"{field}:{reason}")
        self.field = field
        self.reason = reason


def label(document: Mapping, key: str, *, max_chars: int) -> str:
    raw = document.get(key)
    if not isinstance(raw, str):
        raise RecordError(key, "TEXT_REQUIRED")
    value = normalize("NFKC", raw).strip()
    if not value or len(value) > max_chars:
        raise RecordError(key, "TEXT_LENGTH")
    if not all(ch.isprintable() for ch in value):
        raise RecordError(key, "TEXT_CONTROL")
    return value


def magnitude(document: Mapping, key: str, lower: float, upper: float, *, whole: bool) -> int | float:
    raw = document.get(key)
    if isinstance(raw, bool) or raw is None:
        raise RecordError(key, "NUMBER_REQUIRED")
    try:
        number = float(raw)
    except (ValueError, TypeError, OverflowError) as error:
        raise RecordError(key, "NUMBER_INVALID") from error
    if not isfinite(number):
        raise RecordError(key, "NUMBER_NONFINITE")
    if number < lower or number > upper:
        raise RecordError(key, "NUMBER_RANGE")
    if whole:
        if not number.is_integer():
            raise RecordError(key, "INTEGER_REQUIRED")
        return int(number)
    return number


@dataclass(frozen=True, slots=True)
class CatalogVersion:
    alias: str
    master: str
    family: str
    part: str
    begin: int
    end: int
    service_minutes: int
    part_units: int

    @classmethod
    def parse(cls, document: Mapping) -> "CatalogVersion":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        alias = label(document, 'alias', max_chars=40)
        master = label(document, 'master', max_chars=40)
        family = label(document, 'family', max_chars=32)
        part = label(document, 'part', max_chars=36)
        begin = magnitude(document, 'begin', 1, 365, whole=True)
        end = magnitude(document, 'end', 2, 366, whole=True)
        service_minutes = magnitude(document, 'service_minutes', 1, 1000, whole=True)
        part_units = magnitude(document, 'part_units', 1, 30, whole=True)
        return cls(
            alias=alias,
            master=master,
            family=family,
            part=part,
            begin=begin,
            end=end,
            service_minutes=service_minutes,
            part_units=part_units,
        )

    def evidence(self) -> dict:
        return {
            'alias': self.alias,
            'master': self.master,
            'family': self.family,
            'part': self.part,
            'begin': self.begin,
            'end': self.end,
            'service_minutes': self.service_minutes,
            'part_units': self.part_units,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
