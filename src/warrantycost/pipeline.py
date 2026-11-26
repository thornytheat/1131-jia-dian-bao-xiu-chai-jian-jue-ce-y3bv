from pathlib import Path
from json import loads
from hashlib import sha256
from collections import defaultdict

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


def learn(train,validation,rules):
    predictor=model.fit([(history.factors(line.age_month,line.service_minutes,line.symptom),line.cost_cents,1-line.solved) for line in train])
    evidence=[]
    for line in validation:
        estimate,p,d=model.score(predictor,history.factors(line.age_month,line.service_minutes,line.symptom))
        evidence.append((p,1-line.solved,line.cost_cents,estimate))
    metrics=model.validate(evidence)
    residual=metrics["residual_median"] or 0.0
    walk=history.tune_window(validation)
    def forecast(line):
        estimate,risk,distance=model.score(predictor,history.factors(line.age_month,line.service_minutes,line.symptom))
        return estimate,risk,distance
    parameters=[(forecast(line),line) for line in walk.tuning]
    shadow=[(forecast(line),line) for line in walk.validation]
    tuning_blocks=model.monotone_fit([(risk,1-line.solved) for (_,risk,_),line in parameters])
    diagnostics=model.evidence_confidence(
        model.batch_loss([(risk,1-line.solved) for (_,risk,_),line in shadow], tuning_blocks), tuning_blocks)
    bands=band_gates(train,validation,predictor,residual,rules)
    visible=[(forecast(line),(line.solved,line.cost_cents)) for line in train+validation]
    blocks=model.monotone_fit([(risk,1-solved) for (_,risk,_),(solved,_) in visible])
    boundaries=(.3,.4,.46,.5,.6,.7)
    cases=[]
    for line in walk.validation:
        estimate,raw,distance=forecast(line)
        gate=bands.get(history.age_band(line.age_month))
        applied=blocks if gate and gate["启用校准"] else ()
        cases.append((model.calibrated_risk(applied,raw),1-line.solved,max(0.0,estimate+residual),
                      line.cost_cents,4900+line.service_minutes*72,distance))
    alternatives=model.threshold_replay(cases,boundaries=boundaries,distance_limit=rules["radius"])
    audits=dict(验证切分日=walk.pivot_day,空隙工单=len(walk.review),**diagnostics)
    return {"predictor":predictor,"metrics":metrics,"blocks":blocks,"bands":bands,"audits":audits,
            "alternatives":alternatives,"residual":residual}


def band_gates(train,validation,predictor,residual,rules):
    pool=list(train)+list(validation)
    grouped=defaultdict(list)
    for shift in history.shift_replays(pool,validation,min_fit=4):
        trials=[]
        for line in shift.fitting:
            _,risk,_=model.score(predictor,history.factors(line.age_month,line.service_minutes,line.symptom))
            trials.append((risk,1-line.solved))
        blocks=model.monotone_fit(trials)
        for line in shift.replay:
            estimate,raw,distance=model.score(predictor,history.factors(line.age_month,line.service_minutes,line.symptom))
            band=history.age_band(line.age_month)
            grouped[band].append(model.BandCase(shift.day,band,raw,model.calibrated_risk(blocks,raw),1-line.solved,
                                                max(0.0,estimate+residual),line.cost_cents,
                                                4900+line.service_minutes*72,distance))
    return {band:model.band_gate(cases,threshold=rules["probable_failure"],distance_limit=rules["radius"])
            for band,cases in grouped.items()}


def training_sets(logs,rules):
    result={}
    for family in sorted({x.family for x in logs.training}):
        rows=[row for row in logs.training if row.family==family]
        if len(rows)<6:
            continue
        holdout=[row for row in logs.holdout if row.family==family]
        result[family]=learn(rows,holdout,rules)
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
    fitted=training_sets(closed_samples,rules)
    request_docs=[]
    scores=[]
    decode=[]
    for form in accepted:
        variant=mapping.mapped_model(form.appliance,active)
        if not variant or variant["family"] not in fitted:
            stale.append(dict(claim=form.claim,state="机型或维修样本待核对",appliance=form.appliance))
            continue
        learned=fitted[variant["family"]]
        if not learned["metrics"]["support"]:
            stale.append(dict(claim=form.claim,state="验证档期无样本",appliance=form.appliance))
            continue
        cost,p,distance=model.score(learned["predictor"],history.factors(form.age_month,variant["service_minutes"],form.symptom))
        adjusted=max(0.0,cost+learned["residual"])
        raw_risk=p
        band=history.age_band(form.age_month)
        gate=learned["bands"].get(band)
        applied=learned["blocks"] if gate and gate["启用校准"] else ()
        p=model.calibrated_risk(applied,p)
        scores.append(dict(原始风险=round(raw_risk,3),保修单=form.claim,历史组=variant["family"],
                           月龄段=f"{band[0]}–{band[1]}",启用校准=bool(applied),
                           自变量距离=round(distance,3),预测元=round(adjusted/100,2),原估计元=round(cost/100,2),返修风险=round(p,3)))
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
    for family,learned in fitted.items():
        family_diag={**learned["audits"],"采纳校准":any(gate["启用校准"] for gate in learned["bands"].values())}
        fitted_review.append(dict(产品组=family,**learned["metrics"],**family_diag))
        fitted_review.extend(dict(产品组=family,**block.evidence()) for block in learned["blocks"])
        for (low,high),gate in sorted(learned["bands"].items()):
            fitted_review.append(dict(产品组=family,月龄起=low,月龄止=high,**gate))
        threshold_evidence.extend(dict(产品组=family,**row) for row in learned["alternatives"])
    proof=payments.case_signature(statements,{**rules,"cap":allowance},[item[1] for item in (forms,catalogue,repair,invoices,warehouse)])
    band_total=sum(len(learned["bands"]) for learned in fitted.values())
    band_live=sum(sum(gate["启用校准"] for gate in learned["bands"].values()) for learned in fitted.values())
    return {"metrics":{"已预留备件":sum(reserved.values()),"先拆检工单":sum(item["reason"]=="需要先拆检" for item in decisions),
                       "待查结算行":reconciliation["exceptions"],"通过结算金额（元）":reconciliation["cleared"]/100},
            "columns":{"claim":"保修单","appliance":"报修机型","code":"正规机型","part":"兼容件","parts_reserved":"预留件数",
                       "risk":"无效更换概率","cost_yuan":"估算成本（元）","reason":"处置"},"rows":decisions+pending,
            "series":[dict(label=row["claim"],value=row["cost_yuan"]) for row in sorted(decisions,key=lambda item:item["claim"])],
            "stages":[section("保修单",f"受理 {len(accepted)} 件，隔离格式问题 {len(input_rows.rejected)} 件",[row.evidence() for row in accepted]+stale),
                      section("机型映射",f"当日使用 {len(active)} 条有效别名",decode+catalogue_issues),
                      section("返修样本",f"训练 {len(closed_samples.training)}，回放 {len(closed_samples.holdout)}，隔离 {len(closed_samples.excluded)}",[dict(系列=family,成功率=value) for family,value in history.event_rates(closed_samples.training).items()]+history.risk_priors(closed_samples.training)+history.age_ranges(closed_samples.training,closed_samples.holdout)),
                      section("成本拟合",f"共对 {len(scores)} 单做盲估计；{band_live}/{band_total} 个月龄段启用校准",scores+fitted_review+threshold_evidence),
                      section("配件授权",f"班次预留 {sum(reserved.values())} 件，额度 {allowance} 件",decisions+stock_review+inventory_events+warehouse_issues),
                      section("维修结算",f"隔离 {reconciliation['exceptions']} 条对账差异",statements+[row.evidence() for row in accrual]+vendor_balances)],"audit_id":proof,
            "policy_replay":threshold_evidence,"vendor_balances":vendor_balances,"stock_review":stock_review}
