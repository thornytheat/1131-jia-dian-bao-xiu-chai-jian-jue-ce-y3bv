import pytest

from warrantycost.service_balance.service import inspect, reconcile, totals, case_signature
from warrantycost.service_balance.contracts import InvoiceNote, RecordError


@pytest.fixture
def document():
    return {'line': 'LINE', 'claim': 'CLAIM', 'part': 'PART', 'units': 0, 'labor_cents': 0, 'part_cents': 0, 'tax_cents': 0, 'invoice_cents': 0}


def test_contract_round_trip(document):
    entry = InvoiceNote.parse(document)
    assert entry.evidence() == document
    assert InvoiceNote.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['line'] = "　ＡＢＣ-１２　"
    entry = InvoiceNote.parse(document)
    assert getattr(entry, 'line') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['line']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'line'


def test_boolean_is_not_magnitude(document):
    document['units'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        InvoiceNote.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'units': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['units'] = 0 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'units'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_invoice_total_must_match_components(document):
    line=InvoiceNote.parse({**document,"labor_cents":100,"part_cents":200,"tax_cents":20,"invoice_cents":321})
    rows=reconcile([line],[])
    assert rows[0]["reason"]=="金额组成不符"
    assert totals(rows)=={"cleared":0,"held":321,"exceptions":1}


def test_claim_quota_cannot_be_reused_in_multiple_invoices(document):
    line=InvoiceNote.parse({**document,"units":1,"invoice_cents":300,"part_cents":300})
    plan=[dict(claim=line.claim,part=line.part,parts_reserved=1)]
    cleared,held=reconcile([line,replace(line,line="Z-CHARGE")],plan)
    assert cleared["reason"]=="核对通过"
    assert held["reason"]=="备件超出授权"


def test_case_signature_tracks_upstream_policy():
    # TRAP-54
    signature=case_signature([],dict(warranty=24),["batch-1"])
    assert signature!=case_signature([],dict(warranty=36),["batch-1"])
    assert signature!=case_signature([],dict(warranty=24),["batch-2"])
