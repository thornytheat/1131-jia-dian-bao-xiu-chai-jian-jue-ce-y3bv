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
class PredictedClaim:
    claim: str
    family: str
    estimate_cents: float
    part_risk: float
    distance: float
    inspection_fee: int

    @classmethod
    def parse(cls, document: Mapping) -> "PredictedClaim":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        claim = label(document, 'claim', max_chars=38)
        family = label(document, 'family', max_chars=32)
        estimate_cents = magnitude(document, 'estimate_cents', 0, 50000000, whole=False)
        part_risk = magnitude(document, 'part_risk', 0, 1, whole=False)
        distance = magnitude(document, 'distance', 0, 100000, whole=False)
        inspection_fee = magnitude(document, 'inspection_fee', 1, 999999, whole=True)
        return cls(
            claim=claim,
            family=family,
            estimate_cents=estimate_cents,
            part_risk=part_risk,
            distance=distance,
            inspection_fee=inspection_fee,
        )

    def evidence(self) -> dict:
        return {
            'claim': self.claim,
            'family': self.family,
            'estimate_cents': self.estimate_cents,
            'part_risk': self.part_risk,
            'distance': self.distance,
            'inspection_fee': self.inspection_fee,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
