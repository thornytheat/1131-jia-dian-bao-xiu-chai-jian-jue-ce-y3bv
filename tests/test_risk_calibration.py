from itertools import pairwise

import pytest

from warrantycost.claim_cost_model.calibration import (
    batch_loss, calibrated_risk, evidence_confidence, monotone_fit, threshold_replay,
)
from warrantycost.pipeline import run


def test_inverted_probability_buckets_are_pooled_without_borrowing_labels():
    past=[(.25,0),(.25,0),(.40,1),(.40,1),(.55,0),(.55,0),(.80,1),(.80,1)]
    blocks=monotone_fit(past)
    assert [(line.floor,line.ceiling) for line in blocks]==[(.25,.25),(.4,.55),(.8,.8)]
    assert [(line.attempts,line.failures) for line in blocks]==[(2,0),(4,2),(2,2)]
    risks=[calibrated_risk(blocks,steps/100) for steps in range(0,101)]
    assert all(a<=b for a,b in pairwise(risks))
    assert risks[0]==pytest.approx(1/6)
    assert risks[-1]==pytest.approx(5/6)
    assert blocks[1].evidence()["回放单数"]==4
    assert blocks[1].evidence()["校准风险"]==0.5


def test_ties_and_invalid_rows_preserve_exactly_one_contribution():
    candidates=[(.2,1),(.2,0),(.4,0),(.4,3),(float("inf"),1),(-.1,0),(.25,1),(.8,1)]
    trained=monotone_fit(candidates)
    reversed_fit=monotone_fit(list(reversed(candidates)))
    assert trained==reversed_fit
    assert sum(line.attempts for line in trained)==5
    assert sum(line.failures for line in trained)==3
    assert all(a.rate<=b.rate for a,b in pairwise(trained))
    assert calibrated_risk([],0.34)==0.34
    with pytest.raises(ValueError,match="PROBABILITY_RANGE"):
        calibrated_risk(trained,-.01)


def test_acceptance_demands_independent_improvement_and_both_outcomes():
    anchors=[(.25,0)]*5+[(.75,1)]*7
    adjusted=monotone_fit(anchors)
    independent=[(.36,0),(.44,0),(.63,1),(.74,1)]
    comparison=batch_loss(independent, adjusted)
    passed=evidence_confidence(comparison,adjusted)
    assert passed["参数样本数"]==12
    assert passed["参数失败数"]==7
    assert passed["单调区间"]==2
    assert passed["支持"]==4
    assert passed["采纳校准"]
    assert passed["校准后误差"] < passed["校准前误差"]
    bad_outcomes=[(p,1-outcome) for p,outcome in independent]
    worse=batch_loss(bad_outcomes,adjusted)
    assert not evidence_confidence(worse,adjusted)["采纳校准"]
    single=monotone_fit([(.5,1)]*16)
    assert not evidence_confidence(comparison,single)["采纳校准"]


def test_validation_without_failure_reports_undefined_recall():
    report=batch_loss([(.8,0),(.2,0)], [])
    assert report["支持"]==2
    assert report["校准后误差"]==.34
    assert report["高风险召回"] is None
    assert batch_loss([],monotone_fit([(.25,0)]))["校准后误差"] is None


def test_threshold_replay_cost_compares_inspection_with_missing_landed_cost():
    repairs=[(.70,1,25000,28000,3000),(.60,0,17000,16100,2800),(.72,1,2500,6000,3000),(.4,1,27000,28000,1000)]
    lower, middle, higher=threshold_replay(repairs,boundaries=(.61,.45,.71,.45))
    assert lower["拆检笔数"]==2 and lower["拦截失败"]==1
    assert lower["无效拆检"]==1 and lower["漏检成本（分）"]==34000
    assert lower["模拟合计（分）"]==39800
    assert middle["无效拆检"]==0 and middle["模拟合计（分）"]==37000
    assert higher["拆检笔数"]==0 and higher["漏检成本（分）"]==62000
    with pytest.raises(ValueError,match="THRESHOLD_RANGE"):
        threshold_replay(repairs,boundaries=(1.1,))


def test_runtime_replay_is_capacity_independent_and_traces_audit_groups():
    small,large=run(2),run(45)
    evidence=small["policy_replay"]
    assert evidence and evidence==large["policy_replay"]
    assert {row["产品组"] for row in evidence}=={"冰箱","干衣机","洗碗机"}
    for family in {row["产品组"] for row in evidence}:
        rows=[row for row in evidence if row["产品组"]==family]
        assert len(rows)==6
        assert [row["风险阈值"] for row in rows]==[.3,.4,.46,.5,.6,.7]
        assert all(a["拆检笔数"]>=b["拆检笔数"] for a,b in pairwise(rows))


def test_flat_rating_probabilities_do_not_pass_adoption_guard():
    stable=monotone_fit([(.4,result) for result in (1,0,0,0,1,0,0,0,0,1)])
    item,=stable
    assert item.attempts==10 and item.failures==3
    comparison=batch_loss([(.4,0),(.4,0),(.4,1)],stable)
    report=evidence_confidence(comparison,stable)
    assert report["单调区间"]==1
    assert report["参数失败数"]==3
    assert report["支持"]==3
    assert not report["采纳校准"]


def test_runtime_exposes_integral_source_delivery_and_residual_cost():
    snapshot=run(7)
    fitted=snapshot["stages"][3]["records"]
    tracked=[item for item in fitted if "保修单" in item]
    assert len(tracked)>=5
    assert all(0<=item["原始风险"]<=1 for item in tracked)
    uncertainty=[row for row in fitted if "采纳校准" in row]
    assert len(uncertainty)==3
    assert all(row["support"]>=4 for row in uncertainty)
    assert all(row["residual_median"] is not None for row in uncertainty)
    assert any(row["预测元"] != row["原估计元"] for row in tracked)
    assert all("支持" in row for row in uncertainty)
