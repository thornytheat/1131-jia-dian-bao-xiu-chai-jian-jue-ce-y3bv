from collections import defaultdict
from .contracts import CatalogVersion


def catalogue(versions, day):
    aliases = defaultdict(set)
    blocked = []
    for item in versions:
        if item.begin >= item.end:
            blocked.append({"alias":item.alias,"reason":"INVALID_EFFECTIVE_INTERVAL"})
        elif item.begin <= day < item.end:
            aliases[item.alias.casefold()].add(item)
    active = {}
    for key, entries in sorted(aliases.items()):
        if len(entries) == 1:
            active[key] = entries.pop()
        else:
            blocked.append({"alias":key,"reason":"OVERLAPPING_ALIAS_VERSION"})
    return active, sorted(blocked,key=lambda row:(row["alias"],row["reason"]))


def mapped_model(alias: str, active):
    key = alias.casefold().strip()
    selected = active.get(key)
    if selected is None:
        return None
    return {"alias":alias,"master":selected.master,"family":selected.family,"part":selected.part,
            "service_minutes":selected.service_minutes,"part_units":selected.part_units}


def coverage_by_part(active):
    by_part = defaultdict(set)
    for item in active.values():
        by_part[item.part].add(item.master)
    return {part:sorted(models) for part,models in sorted(by_part.items())}
