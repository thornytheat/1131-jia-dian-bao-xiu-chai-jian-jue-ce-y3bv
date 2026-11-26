import pytest

from warrantycost.claim_cost_model.calibration import BandCase, band_gate, threshold_replay
from warrantycost.inspection import inspection_required
from warrantycost.parts_authorization.analysis import economic_choice
from warrantycost.parts_authorization.contracts import PartsRequest
from warrantycost.pipeline import run
from warrantycost.repair_cohorts.chronology import age_band, shift_replays
from warrantycost.repair_cohorts.contracts import RepairLog


def case(shift, *, band=(0, 6), raw=.2, cal=.2, failure=0, estimate=100000, landed=30000,
         fee=5000, distance=1):
    return BandCase(shift, band, raw, cal, failure, estimate, landed, fee, distance)


def work(doc_id, day, *, closed=None, posted=None, age=10, lost=0):
    return RepairLog.parse(dict(work_order=doc_id, family="冰柜", symptom="不制冷", age_month=age,
                                service_minutes=35, accepted=day, closed=closed or day + 1,
                                authorized_published=posted or day + 1, solved=1 - lost,
                                cost_cents=42000, firm=1))


def test_inspection_predicate_is_shared_by_replay_and_authorization():
    limit, threshold = 6.5, .4
    rows = [
        (.70, 1, 25000, 28000, 3000),
        (.10, 0, 25000, 28000, 3000),
        (.90, 1, 25000, 28000, 3000),
    ]
    # rows 1 and 3 clear the threshold and expected waste; row 3 is rejected only by distance
    replay = threshold_replay([*rows[:2], (*rows[2], 8.0)], boundaries=(.4,), distance_limit=limit)
    assert replay[0]["拆检笔数"] == 1
    for risk, estimated, fee, distance in [(.70, 25000, 3000, 1.0), (.10, 25000, 3000, 1.0),
                                           (.90, 25000, 3000, 8.0)]:
        order = PartsRequest.parse(dict(claim="C", appliance="A", code="M", part="P", cost_cents=estimated,
                                        risk=risk, distance=distance, inspection_fee=fee, units=1))
        state, _ = economic_choice(order, distance_limit=limit, threshold=threshold)
        assert (state == "需要先拆检") == inspection_required(
            risk, estimated, fee, distance, threshold=threshold, distance_limit=limit)


@pytest.mark.parametrize("risk,cost,fee,distance,expected", [
    (.5, 10000, 4000, 1, True),
    (.5, 7000, 4000, 1, False),        # expected waste not above the fee
    (.3, 100000, 4000, 1, False),      # below the risk threshold
    (.5, 100000, 4000, 9, False),      # outside the historical radius
])
def test_inspection_predicate_boundaries(risk, cost, fee, distance, expected):
    assert inspection_required(risk, cost, fee, distance, threshold=.4, distance_limit=6.5) is expected


def test_shift_replay_excludes_samples_before_they_are_filed():
    early = work("A", 10, closed=11, posted=11)
    late = work("L", 12, closed=30, posted=30)   # only visible on day 30
    result = shift_replays([early, late], [work("R", 20, closed=21, posted=21)], min_fit=1)
    assert len(result) == 1
    assert result[0].day == 20
    assert late not in result[0].fitting
    assert early in result[0].fitting
    assert [row.work_order for row in result[0].replay] == ["R"]


def test_age_band_uses_half_open_edges_and_folds_the_tail():
    assert age_band(0) == (0, 6)
    assert age_band(6) == (6, 12)
    assert age_band(35) == (24, 36)
    assert age_band(180) == (36, 181)
    assert age_band(240) == (36, 181)


def test_band_gate_enables_only_when_total_cost_falls_without_shift_regression():
    # calibrated risk lifts a failure over the line, cutting the landed miss cost
    improved = [case(1, raw=.30, cal=.55, failure=1), case(1, raw=.30, cal=.55, failure=0)]
    gate = band_gate(improved, threshold=.4, distance_limit=6.5)
    assert gate["启用校准"] and gate["保留原因"] is None
    assert gate["校准合计（分）"] < gate["原风险合计（分）"]


def test_band_gate_keeps_raw_when_any_shift_miss_cost_rises():
    # Shift 2: raw risk triggers inspection; calibration drops it below the line and the
    # expensive failure slips through. Shift 3 is the opposite (calibration rescues a big miss).
    # Totals favour calibration, but shift 2's miss cost rose, so the raw risk must be kept.
    rows = [
        case(2, raw=.50, cal=.20, failure=1, landed=90000),
        case(3, raw=.30, cal=.50, failure=1, landed=200000),
        case(3, raw=.30, cal=.30, failure=0),
    ]
    gate = band_gate(rows, threshold=.4, distance_limit=6.5)
    assert gate["漏检上涨班次"] == [2]
    assert gate["校准合计（分）"] < gate["原风险合计（分）"]
    assert not gate["启用校准"]
    assert gate["保留原因"] == "有班次漏检成本上涨"


def test_band_gate_requires_both_outcomes():
    only_success = [case(1, failure=0), case(2, failure=0)]
    only_failure = [case(1, failure=1), case(2, failure=1)]
    assert band_gate(only_success, threshold=.4, distance_limit=6.5)["保留原因"] == "缺成功或失败样本"
    assert band_gate(only_failure, threshold=.4, distance_limit=6.5)["保留原因"] == "缺成功或失败样本"


def test_band_gate_rejects_calibration_that_does_not_lower_cost():
    flat = [case(1, raw=.30, cal=.35, failure=1, landed=10000), case(1, raw=.30, cal=.35, failure=0)]
    gate = band_gate(flat, threshold=.4, distance_limit=6.5)
    assert not gate["启用校准"]


def test_pipeline_publishes_per_band_decisions_and_stays_capacity_independent():
    small, large = run(2), run(45)
    assert small["stages"][3] == large["stages"][3]
    rows = [row for row in small["stages"][3]["records"] if "月龄起" in row]
    assert rows
    assert all({"启用校准", "保留原因", "原风险合计（分）", "校准合计（分）"} <= set(row) for row in rows)
    for row in rows:
        assert row["月龄起"] < row["月龄止"]
        if row["启用校准"]:
            assert row["成功样本"] > 0 and row["失败样本"] > 0
            assert row["校准合计（分）"] < row["原风险合计（分）"]
            assert not row["漏检上涨班次"]
        else:
            assert row["保留原因"]
    scored = [row for row in small["stages"][3]["records"] if "启用校准" in row and "保修单" in row]
    assert all("月龄段" in row for row in scored)
