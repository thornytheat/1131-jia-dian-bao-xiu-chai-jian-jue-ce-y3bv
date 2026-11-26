import pytest

from warrantycost.repair_cohorts.service import inspect, Split, sample_split, factors, event_rates
from warrantycost.repair_cohorts.contracts import RepairLog, RecordError


@pytest.fixture
def document():
    return {'work_order': 'WORK_ORDER', 'family': 'FAMILY', 'symptom': 'SYMPTOM', 'age_month': 0, 'service_minutes': 1, 'accepted': 1, 'closed': 1, 'authorized_published': 1, 'solved': 0, 'cost_cents': 0, 'firm': 0}


def test_contract_round_trip(document):
    entry = RepairLog.parse(document)
    assert entry.evidence() == document
    assert RepairLog.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['work_order'] = "　ＡＢＣ-１２　"
    entry = RepairLog.parse(document)
    assert getattr(entry, 'work_order') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['work_order']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'work_order'


def test_boolean_is_not_magnitude(document):
    document['age_month'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        RepairLog.parse(document)


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


def test_late_historical_writeback_never_seen_by_training():
    # TRAP-42
    b=RepairLog.parse(dict(work_order="CL-1",family="洗碗",symptom="不加热",age_month=5,service_minutes=10,accepted=1,closed=2,authorized_published=2,cost_cents=100,solved=1,firm=1))
    newer=replace(b,work_order="CL-2",authorized_published=30)
    retro=replace(b,work_order="CL-3",authorized_published=26)
    result=sample_split([b,newer,retro],30,7)
    assert result.training==(b,)
    assert result.holdout==(retro,)
    assert result.excluded==(("CL-2","NOT_VISIBLE_AT_DECISION"),)


def test_not_firm_repair_is_not_a_negative_outcome(document):
    row=RepairLog.parse(document)
    assert sample_split([row],20).excluded[0][1]=="OPEN_OR_INVALID_REPAIR"


def test_log_transform_preserves_service_order():
    assert factors(20,20,"电机异响")[1] < factors(20,45,"电机异响")[1]
    assert factors(20,20,"轻微抖动")[2] == 0
    assert factors(20,20,"电机异响")[2] == 1
