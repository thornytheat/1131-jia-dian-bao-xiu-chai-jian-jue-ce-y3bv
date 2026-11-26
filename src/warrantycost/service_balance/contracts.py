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
class InvoiceNote:
    line: str
    claim: str
    part: str
    units: int
    labor_cents: int
    part_cents: int
    tax_cents: int
    invoice_cents: int

    @classmethod
    def parse(cls, document: Mapping) -> "InvoiceNote":
        if not isinstance(document, Mapping):
            raise RecordError("document", "OBJECT_REQUIRED")
        line = label(document, 'line', max_chars=33)
        claim = label(document, 'claim', max_chars=38)
        part = label(document, 'part', max_chars=34)
        units = magnitude(document, 'units', 0, 50, whole=True)
        labor_cents = magnitude(document, 'labor_cents', 0, 50000000, whole=True)
        part_cents = magnitude(document, 'part_cents', 0, 50000000, whole=True)
        tax_cents = magnitude(document, 'tax_cents', 0, 50000000, whole=True)
        invoice_cents = magnitude(document, 'invoice_cents', 0, 90000000, whole=True)
        return cls(
            line=line,
            claim=claim,
            part=part,
            units=units,
            labor_cents=labor_cents,
            part_cents=part_cents,
            tax_cents=tax_cents,
            invoice_cents=invoice_cents,
        )

    def evidence(self) -> dict:
        return {
            'line': self.line,
            'claim': self.claim,
            'part': self.part,
            'units': self.units,
            'labor_cents': self.labor_cents,
            'part_cents': self.part_cents,
            'tax_cents': self.tax_cents,
            'invoice_cents': self.invoice_cents,
        }


@dataclass(frozen=True, slots=True)
class Rejection:
    row: int
    source: str
    field: str
    reason: str

    def evidence(self) -> dict:
        return {"row": self.row, "source": self.source, "field": self.field, "reason": self.reason}
