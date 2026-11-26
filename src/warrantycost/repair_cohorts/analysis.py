from dataclasses import dataclass
from collections import defaultdict
from math import fsum, log1p
from .contracts import RepairLog


@dataclass(frozen=True)
class Split:
    training: tuple
    holdout: tuple
    excluded: tuple


def sample_split(records, on_day, holdout_days=7):
    bucket=defaultdict(set)
    for row in records:
        bucket[row.work_order].add(row)
    train, validation, excluded = [], [], []
    mark=on_day-holdout_days
    for work_id, variants in sorted(bucket.items()):
        if len(variants)>1:
            excluded.append((work_id,"HISTORY_VERSION_CONFLICT"))
            continue
        row=variants.pop()
        if not row.firm or row.closed < row.accepted:
            excluded.append((work_id,"OPEN_OR_INVALID_REPAIR"))
            continue
        available = max(row.closed,row.authorized_published)
        if available >= on_day:
            excluded.append((work_id,"NOT_VISIBLE_AT_DECISION"))
        elif row.accepted >= mark or available >= mark:
            validation.append(row)
        else:
            train.append(row)
    return Split(tuple(train),tuple(validation),tuple(excluded))


def factors(age, minutes, symptom):
    severe = float(symptom.casefold() in {"不制冷","不加热","电机异响"})
    return (float(age), log1p(minutes), severe)


def event_rates(basket):
    pairs=defaultdict(list)
    for line in basket:
        pairs[line.family].append(line.solved)
    return {family:fsum(values)/len(values) for family,values in sorted(pairs.items())}
