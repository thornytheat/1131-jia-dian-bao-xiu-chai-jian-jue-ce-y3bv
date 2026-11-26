from dataclasses import replace

import pytest

from warrantycost.pipeline import run
from warrantycost.service_balance.contracts import InvoiceNote
from warrantycost.service_balance.service import reconcile
from warrantycost.service_balance.valuation import aggregate_lines, cents_from_yuan, payee_report


def invoice(key, claim, *, quantity=1, part="X-5", base=900, unit_price=500, tax=14, delta=0):
    return InvoiceNote.parse(dict(line=key,claim=claim,part=part,units=quantity,labor_cents=base,
                                   part_cents=unit_price,tax_cents=tax,invoice_cents=base+unit_price+tax+delta))


def test_mixed_hold_and_clear_by_claim_preserve_all_money_components():
    rows=[invoice("A","CLAIM-A"), invoice("B","CLAIM-A",delta=12),invoice("C","CLAIM-B")]
    plan=[{"claim":"CLAIM-A","part":"X-5","parts_reserved":1,"cost_yuan":12.345},
          {"claim":"CLAIM-C","part":"X-5","parts_reserved":2,"cost_yuan":40.82}]
    receipts=reconcile(rows,plan)
    a,b,c=aggregate_lines(plan,rows,receipts,{"CLAIM-A":"北侧服务商","CLAIM-C":"北侧服务商"})
    assert a.booked==1414 and a.frozen==1426
    assert a.projected==1235
    assert a.evidence()["成本差（分）"]==179
    assert a.booked==a.labor+a.parts+a.tax
    assert a.decision=="部分挂账待复核"
    assert b.decision=="完全挂账待复核" and b.seller=="待核实名单"
    assert b.frozen==1414 and b.booked==0
    assert c.decision=="未见结算单" and c.projected==4082
    totals={line["服务商"]:line for line in payee_report([a,b,c])}
    assert totals["北侧服务商"]["暂缓支出（分）"]==1426
    assert totals["北侧服务商"]["核准支出（分）"]==1414
    assert totals["北侧服务商"]["申报工单"]==2
    assert totals["北侧服务商"]["待核实"]==1


def test_mismatched_evidence_cannot_be_used_for_finance_rollup():
    receipt=invoice("A","CLAIM-A")
    old=reconcile([receipt],[])
    with pytest.raises(ValueError,match="INCOMPLETE"):
        aggregate_lines([], [receipt], [], {})
    with pytest.raises(ValueError,match="SOURCE_MISSING"):
        aggregate_lines([], [], old, {})
    with pytest.raises(ValueError,match="DUPLICATE"):
        aggregate_lines([], [receipt], old+old, {})


def test_component_integrity_rejects_tampered_totals():
    input_row=invoice("A","CASE-M")
    decision={"claim":"CASE-M","part":"X-5","parts_reserved":9,"cost_yuan":31.3}
    converted={"line":"A","claim":"CASE-M","invoice_cents":2700,"reason":"核对通过"}
    with pytest.raises(ValueError,match="COMPONENTS"):
        aggregate_lines([decision],[input_row],[converted],{})
    valid=reconcile([input_row],[decision])
    one, = aggregate_lines([decision],[input_row],valid,{})
    with pytest.raises(ValueError,match="PAYEE_SUM"):
        payee_report([replace(one,labor=one.labor+1)])
    assert cents_from_yuan(None)==0
    assert cents_from_yuan(8.005)==801


@pytest.mark.parametrize("limit",[1,4,18,45])
def test_runtime_approved_money_matches_firm_vendor_balance(limit):
    result=run(limit)
    reports=result["vendor_balances"]
    assert sum(line["核准支出（分）"] for line in reports)==round(result["metrics"]["通过结算金额（元）"]*100)
    assert sum(line["暂缓支出（分）"] for line in reports)>0
    assert all(line["待核实"]<=line["申报工单"] for line in reports)
    assert result["metrics"]["已预留备件"]<=limit
