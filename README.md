# tablecheck

Validate **referential integrity** across a set of related CSV/TSV files from a
small JSON schema — primary keys, foreign keys, required columns, and column
types — with **zero dependencies** (Python standard library only).

If your pipeline produces a handful of flat tables that are supposed to line up
(a parent table and several child tables that reference it), `tablecheck` lets
you assert that they actually do, in CI, without standing up a database.

## Install

```bash
pip install .
# or just run it in place:
python -m tablecheck schema.json
```

## Schema

```json
{
  "tables": {
    "study": {
      "path": "study.tsv",
      "primary_key": "id",
      "required": ["id"],
      "types": { "year": "int" }
    },
    "outcome": {
      "path": "outcome.tsv",
      "primary_key": "oid",
      "types": { "value": "float" },
      "foreign_keys": [
        { "column": "study_id", "ref_table": "study", "ref_column": "id" }
      ]
    }
  }
}
```

Paths are resolved relative to the schema file. Delimiter is inferred from the
extension (`.tsv`/`.tab` → tab, otherwise comma).

## Checks

| kind             | meaning                                              |
|------------------|------------------------------------------------------|
| `missing_column` | a required / typed / FK column is absent from header |
| `duplicate_pk`   | the same primary key value appears twice             |
| `empty_pk`       | a primary key or required value is blank             |
| `bad_type`       | a value does not parse as its declared type          |
| `broken_fk`      | a foreign key has no matching parent row             |

Supported types: `int`, `float`, `bool`, `str`. Empty cells are treated as
missing and skip type checks — use `required` to forbid blanks.

## CLI

```bash
$ python -m tablecheck schema.json
[bad_type]   outcome:row 2:value     - 'bad' is not float
[broken_fk]  outcome:row 2:study_id  - 's99' not in study.id
FAIL: 2 violation(s) [bad_type=1, broken_fk=1]
```

Exit code: `0` clean, `1` violations found, `2` usage error — so it drops
straight into a CI step.

## Library

```python
from tablecheck import load_schema, validate

violations = validate(load_schema("schema.json"))
assert not violations, "\n".join(str(v) for v in violations)
```

## Tests

```bash
python tests/test_tablecheck.py     # 5/5
# or: python -m pytest
```

## License

MIT © Mohamadjavad Ershadmanesh
