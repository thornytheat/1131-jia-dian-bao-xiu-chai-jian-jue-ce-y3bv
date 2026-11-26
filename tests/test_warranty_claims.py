import pytest

from warrantycost.warranty_claims.service import inspect, audit_claims, dispatch_queue
from warrantycost.warranty_claims.contracts import ClaimForm, RecordError


@pytest.fixture
def document():
    return {'claim': 'CLAIM', 'appliance': 'APPLIANCE', 'seller': 'SELLER', 'serial': 'SERIAL', 'symptom': 'SYMPTOM', 'age_month': 0, 'received': 1, 'revision': 1, 'inspection_fee': 1, 'safety': 0}


def test_contract_round_trip(document):
    entry = ClaimForm.parse(document)
    assert entry.evidence() == document
    assert ClaimForm.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['claim'] = "　ＡＢＣ-１２　"
    entry = ClaimForm.parse(document)
    assert getattr(entry, 'claim') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['claim']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'claim'


def test_boolean_is_not_magnitude(document):
    document['age_month'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        ClaimForm.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'age_month': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['age_month'] = 0 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'age_month'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_older_snapshot_cannot_undo_safety_flag(document):
    # TRAP-26
    stale=ClaimForm.parse(document)
    current=replace(stale,revision=2,safety=1)
    accepted, held=audit_claims([current,stale],30,36)
    assert accepted==[] and held[0]["state"]=="电气安全人工复核"


def test_two_claims_same_serial_route_only_one(document):
    first=ClaimForm.parse(document)
    later=replace(first,claim="Z-LATER",received=2)
    accepted,held=audit_claims([later,first],30,36)
    assert accepted==[first]
    assert held[0]["state"]=="序列号重复申报"


def test_warranty_term_is_inclusive_at_end_of_month(document):
    first=ClaimForm.parse({**document,"age_month":36})
    assert audit_claims([first],30,36)[0]==[first]
    assert audit_claims([first],30,35)[1][0]["state"]=="超出保修期限"
