import pytest

from warrantycost.parts_authorization.service import inspect, economic_choice, make_plan
from warrantycost.parts_authorization.contracts import PartsRequest, RecordError


@pytest.fixture
def document():
    return {'claim': 'CLAIM', 'appliance': 'APPLIANCE', 'code': 'CODE', 'part': 'PART', 'cost_cents': 0.0, 'risk': 0.0, 'distance': 0.0, 'inspection_fee': 1, 'units': 1}


def test_contract_round_trip(document):
    entry = PartsRequest.parse(document)
    assert entry.evidence() == document
    assert PartsRequest.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['claim'] = "　ＡＢＣ-１２　"
    entry = PartsRequest.parse(document)
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
    document['cost_cents'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        PartsRequest.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'cost_cents': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['cost_cents'] = 0 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'cost_cents'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_high_confidence_outlier_is_never_automatically_approved(document):
    # TRAP-44
    order=PartsRequest.parse({**document,"risk":.01,"distance":11,"units":3})
    plan,used=make_plan([order],{order.part:100},50)
    assert not used and plan[0]["reason"]=="工况超出历史"


def test_parts_authorized_atomically_per_claim(document):
    order=PartsRequest.parse({**document,"units":3,"risk":.1})
    later=replace(order,claim="Z-LATER",risk=.2)
    plan,used=make_plan([later,order],{order.part:20},5)
    assert used=={order.part:3}
    assert [r["reason"] for r in plan]==["批准换件","当班授权额度不足"]


def test_inspection_uses_expected_waste_net_fee(document):
    row=PartsRequest.parse({**document,"cost_cents":10000,"risk":.6,"inspection_fee":1800})
    state,avoid=economic_choice(row,distance_limit=2,threshold=.4)
    assert state=="需要先拆检" and avoid==4200


def test_stock_limit_releases_no_partial_order(document):
    order=PartsRequest.parse({**document,"units":5,"risk":.1})
    plan,used=make_plan([order],{order.part:3},50)
    assert plan[0]["parts_reserved"]==0 and not used
