from collections import Counter, defaultdict
from dataclasses import dataclass

from .contracts import RecordError, label, magnitude


@dataclass(frozen=True, slots=True)
class InventoryPosting:
    ticket: str
    sku: str
    direction: str
    units: int
    posted_day: int
    expected_service_day: int

    @classmethod
    def parse(cls, doc):
        valid_directions={"delivery","reserved","quarantine","release"}
        ticket=label(doc,"ticket",max_chars=44)
        sku=label(doc,"sku",max_chars=38)
        direction=label(doc,"direction",max_chars=16)
        if direction not in valid_directions:
            raise RecordError("direction","STOCK_EVENT_UNKNOWN")
        units=magnitude(doc,"units",1,10000,whole=True)
        posted=magnitude(doc,"posted_day",1,365,whole=True)
        scheduled=magnitude(doc,"expected_service_day",1,365,whole=True)
        return cls(ticket,sku,direction,units,posted,scheduled)


def visible_postings(documents, *, decision_day):
    active=defaultdict(set)
    exceptions=[]
    by_key=defaultdict(int)
    for source,raw in enumerate(documents,start=1):
        if not isinstance(raw,dict):
            exceptions.append({"源行":source,"原因":"不是库存对象"})
            continue
        try:
            entry=InventoryPosting.parse(raw)
        except RecordError as issue:
            exceptions.append({"源行":source,"字段":issue.field,"异常":issue.reason})
            continue
        if entry.posted_day <= decision_day:
            active[entry.ticket].add(entry)
    visible=[]
    for ticket,variants in sorted(active.items()):
        if len(variants) != 1:
            exceptions.append({"库存流水":ticket,"异常":"同流水内容冲突"})
            continue
        posting=variants.pop()
        if posting.expected_service_day > decision_day:
            by_key[posting.sku]+=posting.units
            continue
        visible.append(posting)
    return sorted(visible,key=lambda line:(line.expected_service_day,line.posted_day,line.ticket)),dict(by_key),exceptions


def warehouse_position(balances, events):
    if any(amount<0 for amount in balances.values()):
        raise ValueError("NEGATIVE_PHYSICAL_STOCK")
    quantities=defaultdict(int,balances)
    quarantined=defaultdict(int)
    resolved=Counter()
    evidence=[]
    for posting in events:
        code=posting.sku
        units=posting.units
        state="已过账"
        if posting.direction=="delivery":
            quantities[code]+=units
        elif posting.direction=="release":
            if units>quarantined[code]:
                state="解除数超过隔离库存"
            else:
                quarantined[code]-=units
                quantities[code]+=units
        elif units>quantities[code]:
            state="待查实库存不足"
        else:
            quantities[code]-=units
            if posting.direction=="quarantine":
                quarantined[code]+=units
            else:
                resolved[code]+=units
        evidence.append({"流水":posting.ticket,"备件":code,"动作":posting.direction,"数量":units,
                         "行动后可授权":quantities[code],"是否入账":state})
    return dict(quantities),dict(quarantined),dict(resolved),evidence


def spending_summary(opening, available, reservation, quarantines, incoming):
    parts=set(opening) | set(available) | set(reservation) | set(incoming)
    records=[]
    for sku in sorted(parts):
        stock=available.get(sku,0)
        used=reservation.get(sku,0)
        if not 0<=used<=stock:
            raise ValueError("AUTHORIZATION_EXCEEDS_PHYSICAL_STOCK")
        records.append({"备件":sku,"期初":opening.get(sku,0),"可授权":stock,"本轮预留":used,"可用余额":stock-used,
                        "已有隔离":quarantines.get(sku,0),"后续事件待到期件数":incoming.get(sku,0)})
    return records
