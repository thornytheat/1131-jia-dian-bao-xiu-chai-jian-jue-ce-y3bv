import pytest

from warrantycost.parts_authorization.spares import (
    InventoryPosting, spending_summary, visible_postings, warehouse_position,
)
from warrantycost.pipeline import run


def movement(ticket, direction, units, *, part="锁扣", post=3, valid=3):
    return {"ticket":ticket,"sku":part,"direction":direction,"units":units,"posted_day":post,"expected_service_day":valid}


def test_postings_require_both_registration_and_physical_arrival():
    current=movement("R-01","delivery",8,post=10,valid=11)
    deferred=movement("R-02","delivery",4,post=10,valid=14)
    unpublished=movement("R-03","delivery",6,post=12,valid=10)
    active,future,issues=visible_postings([current,deferred,unpublished],decision_day=11)
    assert [line.ticket for line in active]==["R-01"]
    assert future=={"锁扣":4}
    assert not issues
    actual,future,_=visible_postings([current,deferred,unpublished],decision_day=14)
    assert [line.ticket for line in actual]==["R-03","R-01","R-02"]
    assert not future


def test_duplicate_inventory_conflict_keeps_neither_version():
    base=movement("T-01","delivery",5)
    invalid=movement("T-02","refund",4)
    post,future,issues=visible_postings([base,base,{**base,"units":8},invalid,None],decision_day=11)
    assert not post and not future
    assert len(issues)==3
    assert {row.get("异常", row.get("原因")) for row in issues}=={"同流水内容冲突","STOCK_EVENT_UNKNOWN","不是库存对象"}


def test_quarantine_release_and_committed_parts_have_separate_positions():
    lines=[movement("D0","delivery",10), movement("Q1","quarantine",4), movement("R2","release",1),
           movement("R3","release",7),movement("S4","reserved",3),movement("S5","reserved",20)]
    entries, incoming, _=visible_postings(lines,decision_day=3)
    remaining, quarantine, committed, event_rows=warehouse_position({},entries)
    assert remaining=={"锁扣":4}
    assert quarantine=={"锁扣":3}
    assert committed=={"锁扣":3}
    assert [(x["流水"],x["是否入账"]) for x in event_rows[-3:]]==[("R3","解除数超过隔离库存"),("S4","已过账"),("S5","待查实库存不足")]
    view,=spending_summary({},remaining,{"锁扣":3},quarantine,incoming)
    assert view["可用余额"]==1 and view["已有隔离"]==3
    with pytest.raises(ValueError,match="PHYSICAL_STOCK"):
        spending_summary({},remaining,{"锁扣":5},quarantine,incoming)


def test_live_parts_report_holds_future_stock_outside_usable_quota():
    report=run(13)
    by_part={line["备件"]:line for line in report["stock_review"]}
    circuit=by_part["温控板-T2"]
    assert circuit["可授权"]==7
    assert circuit["后续事件待到期件数"]==12
    assert by_part["阀组-V3"]["已有隔离"]==2
    assert by_part["驱动件-F7"]["可授权"]==12
    assert sum(line["本轮预留"] for line in by_part.values())==report["metrics"]["已预留备件"]
    assert all(row["可用余额"]>=0 for row in by_part.values())
