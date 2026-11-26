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
class PartsRequest:
    claim: str
    appliance: str
    code: str
    part: str
    cost_cents: float
    risk: float
    distance: float
    inspection_fee: int
    units: int

    @classmethod
    def parse(cls, document: Mapping) -> "PartsRequest":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        claim = label(document, 'claim', max_chars=40)
        appliance = label(document, 'appliance', max_chars=36)
        code = label(document, 'code', max_chars=30)
        part = label(document, 'part', max_chars=30)
        cost_cents = magnitude(document, 'cost_cents', 0, 40000000, whole=False)
        risk = magnitude(document, 'risk', 0, 1, whole=False)
        distance = magnitude(document, 'distance', 0, 100000, whole=False)
        inspection_fee = magnitude(document, 'inspection_fee', 1, 1000000, whole=True)
        units = magnitude(document, 'units', 1, 40, whole=True)
        return cls(
            claim=claim,
            appliance=appliance,
            code=code,
            part=part,
            cost_cents=cost_cents,
            risk=risk,
            distance=distance,
            inspection_fee=inspection_fee,
            units=units,
        )

    def evidence(self) -> dict:
        return {
            'claim': self.claim,
            'appliance': self.appliance,
            'code': self.code,
            'part': self.part,
            'cost_cents': self.cost_cents,
            'risk': self.risk,
            'distance': self.distance,
            'inspection_fee': self.inspection_fee,
            'units': self.units,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
