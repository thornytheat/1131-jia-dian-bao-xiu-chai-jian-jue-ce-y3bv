from dataclasses import replace

import pytest

from warrantycost.parts_authorization.contracts import PartsRequest
from warrantycost.parts_authorization.service import make_plan
from warrantycost.pipeline import run


def request(case, part, *, units=2, risk=.21, distance=1, fee=3900, cost=25000):
    return PartsRequest.parse(dict(claim=case,appliance="FR-98",code="主机-NC",part=part,units=units,
                                   risk=risk,distance=distance,inspection_fee=fee,cost_cents=cost))


def test_global_spare_quota_is_shared_across_distinct_product_families():
    ice=request("IA","IC-209",risk=.11,units=4)
    blower=request("IB","FG-802",risk=.12,units=6)
    spare=request("IC","LM-100",risk=.18,units=2)
    limits={"IC-209":12,"FG-802":12,"LM-100":12}
    allocations, consumed=make_plan([spare,blower,ice],limits,7)
    assert consumed=={"IC-209":4,"LM-100":2}
    by_claim={row["claim"]:row for row in allocations}
    assert by_claim["IB"]["parts_reserved"]==0
    assert by_claim["IB"]["reason"]=="当班授权额度不足"
    assert by_claim["IC"]["parts_reserved"]==2
    assert sum(row["parts_reserved"] for row in allocations)==6


def test_repeated_claim_across_incompatible_parts_is_fully_held():
    first=request("F-1","IC-209",risk=.14)
    competing=replace(first,part="FG-802",risk=.11)
    valid=request("F-2","FG-802",risk=.19)
    allocation,used=make_plan([first,valid,competing],{"IC-209":8,"FG-802":8},12)
    repeated=[row for row in allocation if row["claim"]=="F-1"]
    assert len(repeated)==2
    assert all(row["reason"]=="重复申请待查" for row in repeated)
    assert used=={"FG-802":2}
    assert not any(row["parts_reserved"] for row in repeated)
    assert allocation==make_plan([valid,first,competing],{"IC-209":8,"FG-802":8},12)[0]


def test_inspection_reason_takes_priority_over_impossible_stock():
    expensive=request("Z-1","IC-209",cost=42000,risk=.7,fee=4800)
    outlier=request("Z-2","IC-209",cost=33000,risk=.2,fee=2500,distance=18)
    confident=request("Z-3","FG-999",cost=3000,risk=.1,fee=5500)
    choices,used=make_plan([outlier,confident,expensive],{},100)
    by_claim={row["claim"]:row for row in choices}
    assert not used
    assert by_claim["Z-1"]["reason"]=="需要先拆检"
    assert by_claim["Z-2"]["reason"]=="工况超出历史"
    assert by_claim["Z-3"]["reason"]=="备件可用量不足"
    assert by_claim["Z-1"]["net_avoidable_yuan"]==pytest.approx(246)
    assert by_claim["Z-3"]["net_avoidable_yuan"]==-52


@pytest.mark.parametrize("stock, cap, risk", [({"P":-1},3,.3),({"P":1},-1,.3),({"P":1},3,1.01)])
def test_policy_invalidity_protects_before_any_reservation(stock,cap,risk):
    with pytest.raises(ValueError,match="APPROVAL_POLICY_OUT_OF_RANGE"):
        make_plan([request("AA-2","P")],stock,cap,threshold=risk)


def test_live_pending_receipts_cannot_claim_unreserved_parts():
    result=run(1)
    by_claim={row["claim"]:row for row in result["rows"]}
    detail=[row for row in result["stages"][5]["records"] if row.get("reason")=="备件超出授权"]
    assert len(detail)>=5
    assert all(row["claim"] in by_claim and row["invoice_cents"]>0 for row in detail)
    assert all(payee["暂缓支出（分）"]>=0 for payee in result["vendor_balances"])


def test_scores_and_vendor_order_stay_stable_under_repeated_run():
    first=run(19)
    again=run(19)
    assert first==again
    assert len(first["audit_id"])==64
    trial_ids=[row["产品组"] for row in first["policy_replay"]]
    assert trial_ids==sorted(trial_ids)
    by_seller=[row["服务商"] for row in first["vendor_balances"]]
    assert by_seller==sorted(by_seller)
    assert len(set(by_seller))==len(by_seller)


def test_shortage_is_visible_in_snapshot_each_day_budget_changes():
    result=run(2)
    skipped=[row for row in result["rows"] if row["reason"]=="当班授权额度不足"]
    assert skipped
    assert all(row["part"] in {evidence["备件"] for evidence in result["stock_review"]} for row in skipped)
    assert all(row["parts_reserved"]==0 for row in skipped)
