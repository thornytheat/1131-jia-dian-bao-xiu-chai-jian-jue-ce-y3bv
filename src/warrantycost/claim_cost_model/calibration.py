from collections import defaultdict
from dataclasses import dataclass
from itertools import pairwise
from math import fsum, isfinite

from warrantycost.inspection import inspection_required


@dataclass(frozen=True, slots=True)
class RiskBlock:
    floor: float
    ceiling: float
    attempts: int
    failures: int

    @property
    def rate(self):
        return (self.failures + 0.5) / (self.attempts + 1)

    def evidence(self):
        return {"原始下界": self.floor, "原始上界": self.ceiling, "回放单数": self.attempts,
                "实际失败": self.failures, "校准风险": round(self.rate, 5)}


def valid_trials(records):
    return sorted((raw, failed) for raw, failed in records
                  if isfinite(raw) and 0 <= raw <= 1 and failed in (0,1))


def monotone_fit(records):
    equal=defaultdict(list)
    for confidence, outcome in valid_trials(records):
        equal[confidence].append(outcome)
    blocks=[]
    for confidence, values in sorted(equal.items()):
        blocks.append(RiskBlock(confidence, confidence, len(values),sum(values)))
        while len(blocks)>=2 and blocks[-2].rate > blocks[-1].rate:
            newer=blocks.pop()
            former=blocks.pop()
            blocks.append(RiskBlock(former.floor,newer.ceiling,former.attempts+newer.attempts,former.failures+newer.failures))
    return tuple(blocks)


def calibrated_risk(blocks, raw):
    if not isfinite(raw) or not 0 <= raw <= 1:
        raise ValueError("PROBABILITY_RANGE")
    if not blocks:
        return raw
    if raw<=blocks[0].ceiling:
        return blocks[0].rate
    for left,right in pairwise(blocks):
        midpoint=(left.ceiling+right.floor)/2
        if raw<=midpoint:
            return left.rate
        if raw<=right.ceiling:
            return right.rate
    return blocks[-1].rate


def batch_loss(trials, fit):
    valid=valid_trials(trials)
    if not valid:
        return {"支持":0,"校准前误差":None,"校准后误差":None,"高风险召回":None}
    count=len(valid)
    positive=sum(outcome for _,outcome in valid)
    result=[(raw,calibrated_risk(fit,raw),label) for raw,label in valid]
    return {"支持":count,"校准前误差":round(fsum((raw-label)**2 for raw,_,label in result)/count,5),
            "校准后误差":round(fsum((adjusted-label)**2 for _,adjusted,label in result)/count,5),
            "高风险召回":sum(label and adj>=.5 for _,adj,label in result)/positive if positive else None}


def threshold_replay(records, *, boundaries, distance_limit=None):
    limit=float("inf") if distance_limit is None else distance_limit
    grid=[]
    for threshold in sorted(set(boundaries)):
        if not isfinite(threshold) or not 0<=threshold<=1:
            raise ValueError("REPLAY_THRESHOLD_RANGE")
        reviewed=0
        protected=0
        unnecessary=0
        false_negative_loss=0
        aggregate=0
        for record in records:
            risk, failure, estimated_cost, landed_cost, inspection, *tail = record
            distance=tail[0] if tail else 0.0
            eligibility=inspection_required(risk, estimated_cost, inspection, distance,
                                            threshold=threshold, distance_limit=limit)
            if eligibility:
                reviewed+=1
                protected+=failure
                unnecessary+=not failure
                aggregate+=inspection
            elif failure:
                false_negative_loss+=landed_cost
                aggregate+=landed_cost
        grid.append({"风险阈值":threshold,"拆检笔数":reviewed,"拦截失败":protected,
                     "无效拆检":unnecessary,"漏检成本（分）":false_negative_loss,"模拟合计（分）":aggregate})
    return grid


@dataclass(frozen=True, slots=True)
class BandCase:
    shift: int
    band: tuple
    raw: float
    calibrated: float
    failure: int
    estimated_cost: float
    landed_cost: int
    inspection_fee: int
    distance: float


def band_gate(cases, *, threshold, distance_limit):
    """对照同一月龄段在多个历史班次上的「原风险」和「校准风险」总成本。

    只有在成功和失败样本都齐全、总成本确实下降、且没有任何一个班次的漏检成本
    上涨时，才为该月龄段启用校准；否则沿用原始风险。
    """
    successes=sum(1 for case in cases if not case.failure)
    failures=sum(1 for case in cases if case.failure)
    raw_total=cal_total=raw_miss=cal_miss=0
    raw_shift=defaultdict(int)
    cal_shift=defaultdict(int)
    for case in cases:
        if inspection_required(case.raw, case.estimated_cost, case.inspection_fee, case.distance,
                               threshold=threshold, distance_limit=distance_limit):
            raw_total+=case.inspection_fee
        elif case.failure:
            raw_total+=case.landed_cost
            raw_miss+=case.landed_cost
            raw_shift[case.shift]+=case.landed_cost
        if inspection_required(case.calibrated, case.estimated_cost, case.inspection_fee, case.distance,
                               threshold=threshold, distance_limit=distance_limit):
            cal_total+=case.inspection_fee
        elif case.failure:
            cal_total+=case.landed_cost
            cal_miss+=case.landed_cost
            cal_shift[case.shift]+=case.landed_cost
    raised=sorted(shift for shift in set(raw_shift) | set(cal_shift)
                  if cal_shift.get(shift,0)>raw_shift.get(shift,0))
    if not successes or not failures:
        reason="缺成功或失败样本"
    elif cal_total>=raw_total:
        reason="总成本未下降"
    elif raised:
        reason="有班次漏检成本上涨"
    else:
        reason=""
    return {"回放单数":len(cases),"成功样本":successes,"失败样本":failures,
            "原风险合计（分）":raw_total,"校准合计（分）":cal_total,"成本变化（分）":cal_total-raw_total,
            "原风险漏检（分）":raw_miss,"校准漏检（分）":cal_miss,
            "漏检上涨班次":raised,"启用校准":not reason,"保留原因":reason or None}


def symmetric_improvement(comparison):
    raw=comparison["校准前误差"]
    refined=comparison["校准后误差"]
    return raw is not None and raw >= refined


def evidence_confidence(score, risk_blocks):
    distinct_levels=len({(block.floor,block.ceiling) for block in risk_blocks})
    total=sum(block.attempts for block in risk_blocks)
    failed=sum(block.failures for block in risk_blocks)
    use_calibration=total>=8 and failed>0 and failed<total and distinct_levels>=2 and symmetric_improvement(score)
    return {"参数样本数":total,"参数失败数":failed,"单调区间":distinct_levels,
            "采纳校准":use_calibration,**score}
