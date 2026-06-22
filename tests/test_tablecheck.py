"""Unit tests for tablecheck. Run with: python -m pytest  (or python tests/test_tablecheck.py)."""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tablecheck.core import (  # noqa: E402
    Schema, Table, TableSpec, ForeignKey, validate, summarize,
)


def _tables():
    study = Table(
        name="study",
        columns=["id", "year"],
        rows=[{"id": "s1", "year": "2020"}, {"id": "s2", "year": "2021"}],
    )
    outcome = Table(
        name="outcome",
        columns=["oid", "study_id", "value"],
        rows=[
            {"oid": "o1", "study_id": "s1", "value": "1.2"},
            {"oid": "o2", "study_id": "s2", "value": "0.9"},
        ],
    )
    return {"study": study, "outcome": outcome}


def _schema():
    return Schema(tables={
        "study": TableSpec(
            name="study", path="study.tsv", primary_key="id",
            required=["id"], types={"year": "int"},
        ),
        "outcome": TableSpec(
            name="outcome", path="outcome.tsv", primary_key="oid",
            required=["oid"], types={"value": "float"},
            foreign_keys=[ForeignKey("study_id", "study", "id")],
        ),
    })


def test_clean_dataset_has_no_violations():
    assert validate(_schema(), _tables()) == []


def test_broken_foreign_key_is_caught():
    tables = _tables()
    tables["outcome"].rows.append({"oid": "o3", "study_id": "s99", "value": "1.0"})
    vs = validate(_schema(), tables)
    assert any(v.kind == "broken_fk" and v.column == "study_id" for v in vs)


def test_duplicate_primary_key_is_caught():
    tables = _tables()
    tables["study"].rows.append({"id": "s1", "year": "2099"})
    vs = validate(_schema(), tables)
    assert any(v.kind == "duplicate_pk" for v in vs)


def test_bad_type_and_missing_column_are_caught():
    tables = _tables()
    tables["study"].rows[0]["year"] = "twenty"          # not an int
    tables["outcome"].columns = ["oid", "study_id"]      # drop required 'value'? no, drop typed
    vs = validate(_schema(), tables)
    kinds = summarize(vs)
    assert kinds.get("bad_type", 0) >= 1
    assert kinds.get("missing_column", 0) >= 1


def _roundtrip_read():
    """Cover the file-reading path too."""
    with tempfile.TemporaryDirectory() as d:
        sp = os.path.join(d, "study.tsv")
        op = os.path.join(d, "outcome.tsv")
        with open(sp, "w") as fh:
            fh.write("id\tyear\ns1\t2020\ns2\t2021\n")
        with open(op, "w") as fh:
            fh.write("oid\tstudy_id\tvalue\no1\ts1\t1.2\no2\ts2\t0.9\n")
        sch = _schema()
        sch.tables["study"].path = sp
        sch.tables["outcome"].path = op
        return validate(sch)  # tables=None -> read from disk


def test_reads_from_disk():
    assert _roundtrip_read() == []


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    passed = 0
    for fn in fns:
        fn()
        passed += 1
        print(f"  PASS {fn.__name__}")
    print(f"{passed}/{len(fns)} tests passed")
