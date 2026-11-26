from collections import defaultdict
from dataclasses import dataclass
from statistics import median


@dataclass(frozen=True, slots=True)
class Walk:
    tuning: tuple
    validation: tuple
    pivot_day: int | None
    review: tuple


def most_recent_epoch(rows):
    return sorted(rows,key=lambda record:(max(record.closed,record.authorized_published),record.accepted,record.work_order))


def tune_window(holdout, *, min_phase=4):
    if min_phase < 2:
        raise ValueError("CALIBRATION_PHASE_TOO_SHORT")
    chronological=most_recent_epoch(holdout)
    dates=sorted({max(row.closed,row.authorized_published) for row in chronological})
    candidates=[]
    for pivot in dates:
        before=[row for row in chronological if max(row.closed,row.authorized_published)<pivot]
        after=[row for row in chronological if row.accepted>=pivot]
        if len(before)>=min_phase and len(after)>=min_phase:
            candidates.append((len(before)+len(after),min(len(before),len(after)),pivot,before,after))
    if not candidates:
        return Walk((),tuple(chronological),None,())
    score=max(candidates,key=lambda item:(item[1],item[0],-item[2]))
    _,__,date,train,validate=score
    tuned={row.work_order for row in train+validate}
    excluded=tuple(row for row in chronological if row.work_order not in tuned)
    return Walk(tuple(train),tuple(validate),date,excluded)


def risk_priors(rows):
    cells=defaultdict(list)
    for entry in rows:
        cells[entry.family,entry.symptom].append(entry)
    output=[]
    for (family, symptom), items in sorted(cells.items()):
        count=len(items)
        cost=median(row.cost_cents for row in items)
        failure=sum(1-row.solved for row in items)
        output.append({"系列":family,"报修表现":symptom,"完结工单":count,"失败工单":failure,
                       "观察失败率":round(failure/count,4),"成本中值（元）":round(cost/100,2)})
    return output


def age_ranges(training, holdout, *, edges=(0,6,12,24,36,181)):
    if len(edges)<2 or any(left>=right for left,right in zip(edges,edges[1:])):
        raise ValueError("COHORT_BUCKETS_INVALID")
    comparisons=[]
    for low,high in zip(edges,edges[1:]):
        fit=[row for row in training if low<=row.age_month<high]
        replay=[row for row in holdout if low<=row.age_month<high]
        entry={"月龄起":low,"月龄止（不含）":high,"拟合工单":len(fit),"留出工单":len(replay),
               "拟合失败":sum(1-row.solved for row in fit),"留出失败":sum(1-row.solved for row in replay)}
        entry["失衡状态"]="数据可比" if fit and replay else "有缺失分层"
        comparisons.append(entry)
    return comparisons
