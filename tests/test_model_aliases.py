import pytest

from warrantycost.model_aliases.service import inspect, catalogue, mapped_model, coverage_by_part
from warrantycost.model_aliases.contracts import CatalogVersion, RecordError


@pytest.fixture
def document():
    return {'alias': 'ALIAS', 'master': 'MASTER', 'family': 'FAMILY', 'part': 'PART', 'begin': 1, 'end': 2, 'service_minutes': 1, 'part_units': 1}


def test_contract_round_trip(document):
    entry = CatalogVersion.parse(document)
    assert entry.evidence() == document
    assert CatalogVersion.parse(entry.evidence()) == entry


def test_record_identity_normalizes_fullwidth(document):
    document['alias'] = "　ＡＢＣ-１２　"
    entry = CatalogVersion.parse(document)
    assert getattr(entry, 'alias') == "ABC-12"


def test_missing_identity_isolated(document):
    missing = dict(document)
    del missing['alias']
    intake = inspect([missing, document])
    assert intake.read_count == 2
    assert intake.accepted_count == 1
    assert intake.rejection_counts() == {"TEXT_REQUIRED": 1}
    assert intake.rejected[0].row == 1
    assert intake.rejected[0].field == 'alias'


def test_boolean_is_not_magnitude(document):
    document['begin'] = True
    with pytest.raises(RecordError, match="NUMBER_REQUIRED"):
        CatalogVersion.parse(document)


def test_nonfinite_measure_isolated(document):
    corrupted = {**document, 'begin': "nan"}
    batch = inspect([document, corrupted, document])
    assert [item.evidence() for item in batch.records] == [document, document]
    assert batch.rejected[0].row == 2
    assert batch.evidence()["reason_counts"]["NUMBER_NONFINITE"] == 1


def test_invalid_range_reserves_no_entry(document):
    document['begin'] = 1 - 1
    intake = inspect([document])
    assert intake.accepted_count == 0
    assert intake.rejected[0].field == 'begin'
    assert intake.rejected[0].reason == "NUMBER_RANGE"


from dataclasses import replace


def test_catalogue_overlap_blocks_guessing(document):
    # TRAP-25
    record=CatalogVersion.parse({**document,"end":20})
    changed=replace(record,begin=10,part="NONCOMPATIBLE")
    active,blocked=catalogue([record,changed],15)
    assert not active and blocked[0]["reason"]=="OVERLAPPING_ALIAS_VERSION"
    assert len(catalogue([record,changed],20)[0])==0


def test_adjacent_activation_has_only_one_active_version(document):
    old=CatalogVersion.parse({**document,"end":20})
    new=replace(old,begin=20,end=30,part="CURRENT")
    active, blocked=catalogue([old,new],20)
    assert not blocked
    assert mapped_model(old.alias,active)["part"]=="CURRENT"


def test_multiple_catalog_aliases_count_once_per_master(document):
    one=CatalogVersion.parse(document)
    active,_=catalogue([one,replace(one,alias="S-A")],1)
    assert coverage_by_part(active)=={one.part:[one.master]}
