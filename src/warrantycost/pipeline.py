from pathlib import Path
from json import loads
from hashlib import sha256
from math import fsum

from .warranty_claims import service as intake
from .model_aliases import service as mapping
from .repair_cohorts import service as history
from .claim_cost_model import service as model
from .parts_authorization import service as stock
from .service_balance import service as payments

PATH=Path(__file__).resolve().parents[2]


def section(title,summary,records):
    return {"title":title,"summary":summary,"records":records}


def receipt_file(name):
    raw=(PATH/"sample_data"/name).read_bytes()
    lines=[]
    for content in raw.splitlines():
        try:
            lines.append(loads(content))
        except ValueError:
            lines.append(None)
    return lines,sha256(raw).hexdigest()


def learn(train,validation):
    estimator=model.fit([(history.factors(line.age_month,line.service_minutes,line.symptom),line.cost_cents,1-line.solved) for line in train])
    evidence=[]
    for line in validation:
        estimate,p,d=model.score(estimator,history.factors(line.age_month,line.service_minutes,line.symptom))
        evidence.append((p,1-line.solved,line.cost_cents,estimate))
    walk=history.tune_window(validation)
    def forecasts(rows):
        result=[]
        for line in rows:
            estimate,risk,_=model.score(estimator,history.factors(line.age_month,line.service_minutes,line.symptom))
            result.append((estimate,risk,line))
        return result
    parameters=forecasts(walk.tuning)
    shadow=forecasts(walk.validation)
    blocks=model.monotone_fit([(risk,1-line.solved) for _,risk,line in parameters])
    original=[(risk,1-line.solved) for _,risk,line in shadow]
    diagnostics=model.evidence_confidence(model.batch_loss(original,blocks),blocks)
    applied=blocks if diagnostics["采纳校准"] else ()
    boundaries=(.3,.4,.46,.5,.6,.7)
    alternatives=model.threshold_replay([(model.calibrated_risk(applied,risk),1-line.solved,estimate,line.cost_cents,
                                          4900+line.service_minutes*72) for estimate,risk,line in shadow],boundaries=boundaries)
    audits=dict(验证切分日=walk.pivot_day,空隙工单=len(walk.review),**diagnostics)
    return estimator,model.validate(evidence),applied,audits,alternatives


def training_sets(logs):
    result={}
    for family in sorted({x.family for x in logs.training}):
        rows=[row for row in logs.training if row.family==family]
        if len(rows)<6:
            continue
        holdout=[row for row in logs.holdout if row.family==family]
        result[family]=learn(rows,holdout)
    return result


def run(capacity: int | None = None) -> dict:
    rules=loads((PATH/"configs"/"service_queue.json").read_text(encoding="utf-8"))
    allowance=rules["global_cap"] if capacity is None else capacity
    if not 1<=allowance<=100:
        raise ValueError("AUTHORIZATION_CAPACITY_OUT_OF_RANGE")
    forms, catalogue, repair, invoices, warehouse=[receipt_file(name) for name in ("warranty_forms.ndjson","parts_compatibility.ndjson","completed_repair_costs.ndjson","service_invoices.ndjson","warehouse_postings.ndjson")]
    input_rows=intake.inspect(forms[0]); model_rows=mapping.inspect(catalogue[0]); samples=history.inspect(repair[0]); sales=payments.inspect(invoices[0])
    accepted,stale=intake.audit_claims(input_rows.records,rules["day"],rules["term_months"])
    active, catalogue_issues=mapping.catalogue(model_rows.records,rules["day"])
    closed_samples=history.sample_split(samples.records,rules["day"],holdout_days=rules["holdout_days"])
    fitted=training_sets(closed_samples)
    request_docs=[]
    scores=[]
    decode=[]
    for form in accepted:
        variant=mapping.mapped_model(form.appliance,active)
        if not variant or variant["family"] not in fitted:
            stale.append(dict(claim=form.claim,state="机型或维修样本待核对",appliance=form.appliance))
            continue
        estimator,validation,blocks,_,_=fitted[variant["family"]]
        if not validation["support"]:
            stale.append(dict(claim=form.claim,state="验证档期无样本",appliance=form.appliance))
            continue
        cost,p,distance=model.score(estimator,history.factors(form.age_month,variant["service_minutes"],form.symptom))
        adjusted=max(0.0,cost+validation["residual_median"])
        raw_risk=p
        p=model.calibrated_risk(blocks,p)
        scores.append(dict(原始风险=round(raw_risk,3),保修单=form.claim,历史组=variant["family"],自变量距离=round(distance,3),预测元=round(adjusted/100,2),原估计元=round(cost/100,2),返修风险=round(p,3)))
        decode.append(dict(保修单=form.claim,**variant))
        request_docs.append(dict(claim=form.claim,appliance=form.appliance,code=variant["master"],part=variant["part"],units=variant["part_units"],
                              cost_cents=adjusted,risk=p,distance=distance,inspection_fee=form.inspection_fee))
    candidates=stock.inspect(request_docs)
    posted,pending_stock,warehouse_issues=stock.visible_postings(warehouse[0],decision_day=rules["day"])
    availability,quarantined,_,inventory_events=stock.warehouse_position(rules["part_stock"],posted)
    decisions, reserved=stock.make_plan(candidates.records,availability,allowance,threshold=rules["probable_failure"],distance_limit=rules["radius"])
    stock_review=stock.spending_summary(rules["part_stock"],availability,reserved,quarantined,pending_stock)
    pending=[dict(claim=row["claim"],appliance=row.get("appliance","—"),code="—",part="—",parts_reserved=0,risk=None,cost_yuan=None,reason=row["state"]) for row in sorted(stale,key=lambda row:row["claim"])]
    statements=payments.reconcile(sales.records,decisions)
    reconciliation=payments.totals(statements)
    accrual=payments.aggregate_lines(decisions, sales.records, statements, {row.claim:row.seller for row in accepted})
    vendor_balances=payments.payee_report(accrual)
    threshold_evidence=[]
    fitted_review=[]
    for family,(_,metrics,blocks,audit,options) in fitted.items():
        fitted_review.append(dict(产品组=family,**metrics,**audit))
        fitted_review.extend(dict(产品组=family,**block.evidence()) for block in blocks)
        threshold_evidence.extend(dict(产品组=family,**row) for row in options)
    proof=payments.case_signature(statements,{**rules,"cap":allowance},[item[1] for item in (forms,catalogue,repair,invoices,warehouse)])
    return {"metrics":{"已预留备件":sum(reserved.values()),"先拆检工单":sum(item["reason"]=="需要先拆检" for item in decisions),
                       "待查结算行":reconciliation["exceptions"],"通过结算金额（元）":reconciliation["cleared"]/100},
            "columns":{"claim":"保修单","appliance":"报修机型","code":"正规机型","part":"兼容件","parts_reserved":"预留件数",
                       "risk":"无效更换概率","cost_yuan":"估算成本（元）","reason":"处置"},"rows":decisions+pending,
            "series":[dict(label=row["claim"],value=row["cost_yuan"]) for row in sorted(decisions,key=lambda item:item["claim"])],
            "stages":[section("保修单",f"受理 {len(accepted)} 件，隔离格式问题 {len(input_rows.rejected)} 件",[row.evidence() for row in accepted]+stale),
                      section("机型映射",f"当日使用 {len(active)} 条有效别名",decode+catalogue_issues),
                      section("返修样本",f"训练 {len(closed_samples.training)}，回放 {len(closed_samples.holdout)}，隔离 {len(closed_samples.excluded)}",[dict(系列=family,成功率=value) for family,value in history.event_rates(closed_samples.training).items()]+history.risk_priors(closed_samples.training)+history.age_ranges(closed_samples.training,closed_samples.holdout)),
                      section("成本拟合",f"共对 {len(scores)} 单做盲估计",scores+fitted_review+threshold_evidence),
                      section("配件授权",f"班次预留 {sum(reserved.values())} 件，额度 {allowance} 件",decisions+stock_review+inventory_events+warehouse_issues),
                      section("维修结算",f"隔离 {reconciliation['exceptions']} 条对账差异",statements+[row.evidence() for row in accrual]+vendor_balances)],"audit_id":proof,
            "policy_replay":threshold_evidence,"vendor_balances":vendor_balances,"stock_review":stock_review}
