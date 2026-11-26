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
class RepairLog:
    work_order: str
    family: str
    symptom: str
    age_month: int
    service_minutes: int
    accepted: int
    closed: int
    authorized_published: int
    solved: int
    cost_cents: int
    firm: int

    @classmethod
    def parse(cls, document: Mapping) -> "RepairLog":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        work_order = label(document, 'work_order', max_chars=42)
        family = label(document, 'family', max_chars=30)
        symptom = label(document, 'symptom', max_chars=36)
        age_month = magnitude(document, 'age_month', 0, 180, whole=True)
        service_minutes = magnitude(document, 'service_minutes', 1, 1000, whole=True)
        accepted = magnitude(document, 'accepted', 1, 365, whole=True)
        closed = magnitude(document, 'closed', 1, 365, whole=True)
        authorized_published = magnitude(document, 'authorized_published', 1, 365, whole=True)
        solved = magnitude(document, 'solved', 0, 1, whole=True)
        cost_cents = magnitude(document, 'cost_cents', 0, 200000000, whole=True)
        firm = magnitude(document, 'firm', 0, 1, whole=True)
        return cls(
            work_order=work_order,
            family=family,
            symptom=symptom,
            age_month=age_month,
            service_minutes=service_minutes,
            accepted=accepted,
            closed=closed,
            authorized_published=authorized_published,
            solved=solved,
            cost_cents=cost_cents,
            firm=firm,
        )

    def evidence(self) -> dict:
        return {
            'work_order': self.work_order,
            'family': self.family,
            'symptom': self.symptom,
            'age_month': self.age_month,
            'service_minutes': self.service_minutes,
            'accepted': self.accepted,
            'closed': self.closed,
            'authorized_published': self.authorized_published,
            'solved': self.solved,
            'cost_cents': self.cost_cents,
            'firm': self.firm,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
