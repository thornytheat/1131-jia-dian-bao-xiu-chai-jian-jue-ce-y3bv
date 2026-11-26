from warrantycost.pipeline import run


def test_sample_work_orders_stop_safety_duplication_and_alias_conflicts():
    result=run(9)
    assert len(result["stages"])==6
    assert 0 < result["metrics"]["已预留备件"] <= 9
    reasons={row["reason"] for row in result["rows"]}
    assert {"电气安全人工复核","机型或维修样本待核对","序列号重复申报"} <= reasons
    assert result["metrics"]["待查结算行"] >= 2


def test_warehouse_restriction_does_not_retrain_curves():
    low,high=run(1),run(100)
    assert low["stages"][3]==high["stages"][3]
    assert low["metrics"]["已预留备件"] < high["metrics"]["已预留备件"]
    assert low["audit_id"] != high["audit_id"]
