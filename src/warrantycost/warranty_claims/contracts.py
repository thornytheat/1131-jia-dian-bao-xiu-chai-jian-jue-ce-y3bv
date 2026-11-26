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
class ClaimForm:
    claim: str
    appliance: str
    seller: str
    serial: str
    symptom: str
    age_month: int
    received: int
    revision: int
    inspection_fee: int
    safety: int

    @classmethod
    def parse(cls, document: Mapping) -> "ClaimForm":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        claim = label(document, 'claim', max_chars=36)
        appliance = label(document, 'appliance', max_chars=40)
        seller = label(document, 'seller', max_chars=32)
        serial = label(document, 'serial', max_chars=36)
        symptom = label(document, 'symptom', max_chars=40)
        age_month = magnitude(document, 'age_month', 0, 240, whole=True)
        received = magnitude(document, 'received', 1, 365, whole=True)
        revision = magnitude(document, 'revision', 1, 100, whole=True)
        inspection_fee = magnitude(document, 'inspection_fee', 1, 999999, whole=True)
        safety = magnitude(document, 'safety', 0, 1, whole=True)
        return cls(
            claim=claim,
            appliance=appliance,
            seller=seller,
            serial=serial,
            symptom=symptom,
            age_month=age_month,
            received=received,
            revision=revision,
            inspection_fee=inspection_fee,
            safety=safety,
        )

    def evidence(self) -> dict:
        return {
            'claim': self.claim,
            'appliance': self.appliance,
            'seller': self.seller,
            'serial': self.serial,
            'symptom': self.symptom,
            'age_month': self.age_month,
            'received': self.received,
            'revision': self.revision,
            'inspection_fee': self.inspection_fee,
            'safety': self.safety,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
