from collections import defaultdict
from hashlib import blake2b
from json import dumps
from .contracts import InvoiceNote


def reconcile(lines, plan):
    consumed=defaultdict(int)
    notes=defaultdict(set)
    for item in lines:
        notes[item.line].add(item)
    decisions={record["claim"]:record for record in plan}
    records=[]
    for line_id, claims in sorted(notes.items()):
        if len(claims)>1:
            records.append(dict(line=line_id,claim="—",reason="结算行冲突",invoice_cents=0))
            continue
        item=claims.pop()
        choice=decisions.get(item.claim)
        from_components=item.labor_cents+item.part_cents+item.tax_cents
        if item.invoice_cents!=from_components:
            state="金额组成不符"
        elif choice is None:
            state="保修单未受理"
        elif item.units and (item.part!=choice["part"] or consumed[item.claim]+item.units>choice["parts_reserved"]):
            state="备件超出授权"
        else:
            state="核对通过"
            consumed[item.claim]+=item.units
        records.append(dict(line=item.line,claim=item.claim,reason=state,invoice_cents=item.invoice_cents))
    return records


def totals(records):
    actual=sum(x["invoice_cents"] for x in records)
    cleared=sum(x["invoice_cents"] for x in records if x["reason"]=="核对通过")
    return {"cleared":cleared,"held":actual-cleared,"exceptions":sum(x["reason"]!="核对通过" for x in records)}


def case_signature(evidence, rules, samples):
    normalized=dumps({"model":"warranty-ridge-v1","files":samples,"rules":rules,"outcome":evidence},sort_keys=True,
                       separators=(",",":"),ensure_ascii=False,allow_nan=False)
    return blake2b(normalized.encode(),digest_size=32).hexdigest()
