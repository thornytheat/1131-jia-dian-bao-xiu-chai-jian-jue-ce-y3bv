from collections import defaultdict
from .contracts import ClaimForm


def audit_claims(forms, day, term_months):
    revisions = defaultdict(set)
    for form in forms:
        if form.received <= day:
            revisions[form.claim].add(form)
    usable, held = [], []
    for key, changes in sorted(revisions.items()):
        current = max(x.revision for x in changes)
        latest = [x for x in changes if x.revision == current]
        serials = {x.serial for x in latest}
        if len(serials) != 1 or len(latest) != 1:
            held.append(dict(claim=key,state="修订冲突"))
        elif latest[0].safety:
            held.append(dict(claim=key,state="电气安全人工复核", appliance=latest[0].appliance))
        elif latest[0].age_month > term_months:
            held.append(dict(claim=key,state="超出保修期限", appliance=latest[0].appliance))
        else:
            usable.append(latest[0])
    by_serial = defaultdict(list)
    for row in usable:
        by_serial[row.serial].append(row)
    canonical = []
    for copies in by_serial.values():
        first = min(copies,key=lambda line:(line.received,line.claim))
        canonical.append(first)
        held.extend(dict(claim=duplicate.claim,appliance=duplicate.appliance,state="序列号重复申报") for duplicate in copies if duplicate!=first)
    return sorted(canonical,key=lambda row:row.claim), sorted(held,key=lambda row:row["claim"])


def dispatch_queue(forms):
    counts=defaultdict(int)
    for form in forms:
        counts[form.seller] += 1
    return [{"seller":seller,"count":value} for seller,value in sorted(counts.items(),key=lambda x:(-x[1],x[0]))]
