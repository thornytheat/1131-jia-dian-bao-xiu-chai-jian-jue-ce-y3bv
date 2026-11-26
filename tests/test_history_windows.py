from dataclasses import replace

import pytest

from warrantycost.repair_cohorts.chronology import age_ranges, most_recent_epoch, risk_priors, tune_window
from warrantycost.repair_cohorts.contracts import RepairLog


def work(doc_id, day, *, age=10, closed=None, posted=None, product="冰柜", symptom="不制冷", lost=0, price=42000):
    return RepairLog.parse(dict(work_order=doc_id,family=product,symptom=symptom,age_month=age,service_minutes=35,
                                accepted=day,closed=closed or day+1,authorized_published=posted or day+1,
                                solved=1-lost,cost_cents=price,firm=1))


def test_split_separates_acceptance_tuning_and_actual_publication():
    rows=[work(f"H-{day:02}",day,age=day%10) for day in range(31,47)]
    long_running=work("LATE-ONSET",32,posted=45,price=50000)
    audit=tune_window(rows+[long_running],min_phase=4)
    assert audit.tuning and audit.validation and audit.review
    assert all(max(line.closed,line.authorized_published)<audit.pivot_day for line in audit.tuning)
    assert all(line.accepted>=audit.pivot_day for line in audit.validation)
    assert long_running in audit.review
    assert len(audit.tuning+audit.validation+audit.review)==17
    reversed_input=tune_window(list(reversed(rows+[long_running])),min_phase=4)
    assert reversed_input==audit


def test_sparse_calibration_never_discards_evaluation_cases():
    small=[work("P-20",17,posted=22), work("P-19",19,posted=21)]
    result=tune_window(small,min_phase=2)
    assert result.tuning==()
    assert result.pivot_day is None
    assert [row.work_order for row in result.validation]==["P-19","P-20"]
    assert result.review==()
    with pytest.raises(ValueError,match="CALIBRATION_PHASE"):
        tune_window(small,min_phase=1)


def test_fault_priors_use_median_and_documented_failure_counts():
    data=[work("X",1,price=1500),work("Y",1,price=55000,lost=1),work("Z",1,price=35000),
          work("N",1,price=4000,symptom="异响")]
    picture=risk_priors(data)
    collapse={line["报修表现"]:line for line in picture}
    cold=collapse["不制冷"]
    assert cold["完结工单"]==3 and cold["失败工单"]==1
    assert cold["成本中值（元）"]==350
    assert cold["观察失败率"]==.3333
    assert collapse["异响"]["完结工单"]==1
    assert risk_priors(data)==risk_priors(list(reversed(data)))


def test_age_boundaries_keep_maturing_claim_in_only_one_slice():
    watch=[work("Q-01",3,age=5,lost=1),work("Q-02",4,age=6),work("Q-03",5,age=12,lost=1)]
    forward=[work("T-04",20,age=12,lost=1),work("T-05",21,age=6,lost=1)]
    lines=age_ranges(watch,forward,edges=(0,6,12,24))
    assert [r["拟合工单"] for r in lines]==[1,1,1]
    assert [r["留出工单"] for r in lines]==[0,1,1]
    assert [r["留出失败"] for r in lines]==[0,1,1]
    assert lines[0]["失衡状态"]=="有缺失分层"
    assert lines[1]["失衡状态"]=="数据可比"
    assert sum(row["拟合失败"] for row in lines)==2
    with pytest.raises(ValueError,match="BUCKETS_INVALID"):
        age_ranges(watch,forward,edges=(0,6,6))
