from collections import Counter
from .contracts import PartsRequest


def economic_choice(row: PartsRequest, *, distance_limit, threshold):
    expected_loss = row.cost_cents * row.risk
    avoidable = expected_loss-row.inspection_fee
    if row.distance > distance_limit:
        return "工况超出历史", avoidable
    if row.risk >= threshold and avoidable > 0:
        return "需要先拆检", avoidable
    return "可申请更换", avoidable


def make_plan(requests, stock, allowance, *, threshold=.40, distance_limit=6.5):
    if not 0 <= threshold <= 1 or allowance < 0 or any(n < 0 for n in stock.values()):
        raise ValueError("APPROVAL_POLICY_OUT_OF_RANGE")
    duplicated=Counter(row.claim for row in requests)
    used=Counter()
    used_total=0
    decisions=[]
    conflicts=[]
    for row in requests:
        state, avoidable=economic_choice(row,distance_limit=distance_limit,threshold=threshold)
        conflicts.append((state,avoidable,row))
    for state, avoidable, row in sorted(conflicts,key=lambda item:(item[0]!="可申请更换",item[2].risk,item[2].claim)):
        reserved=0
        if duplicated[row.claim]>1:
            state="重复申请待查"
        elif state=="可申请更换":
            if row.units > stock.get(row.part,0)-used[row.part]:
                state="备件可用量不足"
            elif row.units > allowance-used_total:
                state="当班授权额度不足"
            else:
                state="批准换件"
                reserved=row.units
                used[row.part]+=reserved
                used_total+=reserved
        decisions.append(dict(claim=row.claim,appliance=row.appliance,code=row.code,part=row.part,parts_reserved=reserved,
                              risk=round(row.risk,4),cost_yuan=round(row.cost_cents/100,2),net_avoidable_yuan=round(avoidable/100,2),reason=state))
    return decisions, dict(used)
