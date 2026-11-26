import pytest

from warrantycost.claim_cost_model.service import inspect, Predictor, stable_probability, fit, score, validate
from warrantycost.claim_cost_model.contracts import PredictedClaim, RecordError


@pytest.fixture
def document():
    return {'claim': 'CLAIM', 'family': 'FAMILY', 'estimate_cents': 0.0, 'part_risk': 0.0, 'distance': 0.0, 'inspection_fee': 1}


def test_contract_round_trip(document):
    entry = PredictedClaim.parse(document)
    assert entry.evidence() == document
    assert PredictedClaim.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['claim'] = "　ＡＢＣ-１２　"
    entry = PredictedClaim.parse(document)
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
    document['estimate_cents'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        PredictedClaim.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'estimate_cents': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['estimate_cents'] = 0 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'estimate_cents'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


def test_sigmoid_uses_stable_exponent():
    # TRAP-31
    assert stable_probability(-900)==0 and stable_probability(900)==1
    assert stable_probability(0)==.5


def test_zero_variance_does_not_shift_cost_prediction():
    # TRAP-32
    estimator=fit([((1e8, x),100+x*80,int(x%2)) for x in range(12)])
    assert estimator.scale[0]==1e-5 and estimator.cost_weights[0]==0
    assert score(estimator,(1e8,8))[0] > score(estimator,(1e8,4))[0]


def test_no_positive_repairs_reports_unknown_recall():
    # TRAP-43
    result=validate([(0.2,0,100,102),(0.8,0,100,98)])
    assert result["recall"] is None and result["support"]==2
    assert result["brier"]==pytest.approx(.34)
    assert validate([])["brier"] is None


def test_prediction_not_affected_by_other_service_case():
    # TRAP-53
    estimator=fit([((x,5*x),100+x*80,int(x%2)) for x in range(12)])
    few=[score(estimator,row) for row in [(8,40)]]
    many=[score(estimator,row) for row in [(100,500),(8,40),(0,0)]]
    assert few[0]==many[1]
