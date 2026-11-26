from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


@dataclass(frozen=True, slots=True)
class Accrual:
    claim: str
    seller: str
    projected: int
    booked: int
    frozen: int
    labor: int
    parts: int
    tax: int
    decision: str

    def evidence(self):
        return {"保修单":self.claim,"服务商":self.seller,"成本预测（分）":self.projected,"核准入账（分）":self.booked,
                "暂挂（分）":self.frozen,"工时（分）":self.labor,"配件（分）":self.parts,"税额（分）":self.tax,
                "成本差（分）":self.booked-self.projected,"处理":self.decision}


def cents_from_yuan(sum_yuan):
    if sum_yuan is None:
        return 0
    scaled=Decimal(str(sum_yuan))*100
    return int(scaled.quantize(1,rounding=ROUND_HALF_UP))


def aggregate_lines(contracts, invoices, receipts, claim_sellers):
    decisions={line["claim"]:line for line in contracts}
    unique=defaultdict(set)
    for invoice in invoices:
        unique[invoice.line].add(invoice)
    distributed=defaultdict(list)
    seen=set()
    for summary in receipts:
        row_id=summary["line"]
        if row_id in seen:
            raise ValueError("DUPLICATE_RECONCILIATION_OUTCOME")
        seen.add(row_id)
        if row_id not in unique:
            raise ValueError("RECONCILIATION_SOURCE_MISSING")
        distributed[summary["claim"]].append(summary)
    if seen!=unique.keys():
        raise ValueError("INCOMPLETE_RECONCILIATION")
    rows=[]
    for claim in sorted(distributed.keys() | decisions.keys()):
        accepted=[line for line in distributed[claim] if line["reason"]=="核对通过"]
        pending=[line for line in distributed[claim] if line["reason"]!="核对通过"]
        cost=int(sum(line["invoice_cents"] for line in accepted))
        reserve=int(sum(line["invoice_cents"] for line in pending))
        details=[next(iter(unique[line["line"]])) for line in accepted]
        labor=sum(line.labor_cents for line in details)
        tax=sum(line.tax_cents for line in details)
        parts=sum(line.part_cents for line in details)
        if cost != labor+tax+parts:
            raise ValueError("APPROVED_COMPONENTS_MISMATCH")
        if pending and accepted:
            status="部分挂账待复核"
        elif pending:
            status="完全挂账待复核"
        elif accepted:
            status="已入账"
        else:
            status="未见结算单"
        price=cents_from_yuan(decisions.get(claim,{}).get("cost_yuan"))
        rows.append(Accrual(claim,claim_sellers.get(claim,"待核实名单"),price,cost,reserve,labor,parts,tax,status))
    return rows


def payee_report(evidence):
    by_seller=defaultdict(list)
    for record in evidence:
        by_seller[record.seller].append(record)
    overview=[]
    for seller,ledger in sorted(by_seller.items()):
        credited=sum(line.booked for line in ledger)
        frozen=sum(line.frozen for line in ledger)
        volume=sum(line.tax+line.parts+line.labor for line in ledger)
        if credited!=volume:
            raise ValueError("PAYEE_SUM_MISMATCH")
        reasons=Counter(line.decision for line in ledger)
        overview.append({"服务商":seller,"核准支出（分）":credited,"暂缓支出（分）":frozen,
                         "申报工单":len(ledger),"全部入账":reasons["已入账"],"待核实":sum(reasons.get(label,0)
                          for label in ("部分挂账待复核","完全挂账待复核"))})
    return overview
