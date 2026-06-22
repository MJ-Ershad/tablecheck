"""Core validation logic for tablecheck.

Standard library only. The public surface is :func:`load_schema`,
:func:`read_table`, and :func:`validate`.
"""

from __future__ import annotations

import csv
import json
import os
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional


# --------------------------------------------------------------------------- #
# Data model
# --------------------------------------------------------------------------- #
@dataclass
class ForeignKey:
    """A reference from ``column`` in this table to ``ref_table.ref_column``."""

    column: str
    ref_table: str
    ref_column: str


@dataclass
class TableSpec:
    """Schema for a single table."""

    name: str
    path: str
    primary_key: Optional[str] = None
    required: List[str] = field(default_factory=list)
    types: Dict[str, str] = field(default_factory=dict)
    foreign_keys: List[ForeignKey] = field(default_factory=list)


@dataclass
class Schema:
    """A collection of table specs, keyed by table name."""

    tables: Dict[str, TableSpec]

    def order(self) -> List[str]:
        """Table names sorted so that referenced tables come first.

        A simple Kahn topological sort over foreign-key edges. Cycles are
        tolerated: any tables left in a cycle are appended in declaration order.
        """
        remaining = dict(self.tables)
        deps = {
            name: {fk.ref_table for fk in spec.foreign_keys if fk.ref_table in remaining}
            for name, spec in remaining.items()
        }
        ordered: List[str] = []
        while remaining:
            free = [n for n in remaining if not (deps[n] - set(ordered))]
            if not free:  # cycle; fall back to declaration order
                free = list(remaining)
            for n in sorted(free):
                ordered.append(n)
                remaining.pop(n, None)
        return ordered


@dataclass
class Table:
    """An in-memory table: header plus a list of row dicts."""

    name: str
    columns: List[str]
    rows: List[Dict[str, str]]


@dataclass
class Violation:
    """A single failed check."""

    table: str
    kind: str           # missing_column | duplicate_pk | empty_pk | bad_type | broken_fk
    message: str
    row: Optional[int] = None   # 1-based data row, when applicable
    column: Optional[str] = None

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        loc = self.table
        if self.row is not None:
            loc += f":row {self.row}"
        if self.column:
            loc += f":{self.column}"
        return f"[{self.kind}] {loc} - {self.message}"


# --------------------------------------------------------------------------- #
# Loading
# --------------------------------------------------------------------------- #
def load_schema(path: str) -> Schema:
    """Read a JSON schema file into a :class:`Schema`.

    Expected shape::

        {
          "tables": {
            "study":   {"path": "study.tsv", "primary_key": "id",
                        "required": ["id"], "types": {"year": "int"}},
            "outcome": {"path": "outcome.tsv", "primary_key": "oid",
                        "foreign_keys": [
                          {"column": "study_id", "ref_table": "study",
                           "ref_column": "id"}]}
          }
        }
    """
    with open(path, "r", encoding="utf-8") as fh:
        raw = json.load(fh)

    base_dir = os.path.dirname(os.path.abspath(path))
    tables: Dict[str, TableSpec] = {}
    for name, spec in raw.get("tables", {}).items():
        rel = spec.get("path", f"{name}.tsv")
        fks = [
            ForeignKey(fk["column"], fk["ref_table"], fk["ref_column"])
            for fk in spec.get("foreign_keys", [])
        ]
        tables[name] = TableSpec(
            name=name,
            path=rel if os.path.isabs(rel) else os.path.join(base_dir, rel),
            primary_key=spec.get("primary_key"),
            required=list(spec.get("required", [])),
            types=dict(spec.get("types", {})),
            foreign_keys=fks,
        )
    return Schema(tables=tables)


def read_table(name: str, path: str) -> Table:
    """Read a CSV or TSV file. Delimiter is inferred from the extension."""
    delimiter = "\t" if path.lower().endswith((".tsv", ".tab")) else ","
    with open(path, "r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh, delimiter=delimiter)
        columns = list(reader.fieldnames or [])
        rows = [dict(r) for r in reader]
    return Table(name=name, columns=columns, rows=rows)


# --------------------------------------------------------------------------- #
# Type checking
# --------------------------------------------------------------------------- #
def _parses_as(value: str, type_name: str) -> bool:
    """True if ``value`` is an acceptable instance of ``type_name``.

    Empty strings are treated as missing and pass type checks (use ``required``
    to forbid them). Supported types: int, float, bool, str.
    """
    if value is None or value == "":
        return True
    try:
        if type_name == "int":
            int(value)
        elif type_name == "float":
            float(value)
        elif type_name == "bool":
            return value.strip().lower() in {"0", "1", "true", "false", "yes", "no"}
        elif type_name == "str":
            return True
        else:  # unknown declared type -> don't block
            return True
        return True
    except (ValueError, TypeError):
        return False


# --------------------------------------------------------------------------- #
# Validation
# --------------------------------------------------------------------------- #
def validate(schema: Schema, tables: Optional[Dict[str, Table]] = None) -> List[Violation]:
    """Run every check and return a flat list of violations (empty == clean).

    If ``tables`` is omitted, each table is read from the path in its spec.
    """
    if tables is None:
        tables = {
            name: read_table(name, spec.path) for name, spec in schema.tables.items()
        }

    violations: List[Violation] = []
    pk_index: Dict[str, set] = {}

    for name in schema.order():
        spec = schema.tables[name]
        table = tables.get(name)
        if table is None:
            violations.append(
                Violation(name, "missing_column", "table not loaded")
            )
            continue

        cols = set(table.columns)

        # required columns present in the header
        for col in spec.required:
            if col not in cols:
                violations.append(
                    Violation(name, "missing_column", f"required column '{col}' absent")
                )

        # declared-type columns present
        for col in spec.types:
            if col not in cols:
                violations.append(
                    Violation(name, "missing_column", f"typed column '{col}' absent")
                )

        # primary-key uniqueness + presence
        seen: set = set()
        pk = spec.primary_key
        for i, row in enumerate(table.rows, start=1):
            # required non-empty values
            for col in spec.required:
                if col in cols and (row.get(col) or "") == "":
                    violations.append(
                        Violation(name, "empty_pk" if col == pk else "bad_type",
                                  f"required value missing", row=i, column=col)
                    )
            # types
            for col, tname in spec.types.items():
                if col in cols and not _parses_as(row.get(col, ""), tname):
                    violations.append(
                        Violation(name, "bad_type",
                                  f"'{row.get(col)}' is not {tname}", row=i, column=col)
                    )
            # pk uniqueness
            if pk and pk in cols:
                key = row.get(pk, "")
                if key == "":
                    violations.append(
                        Violation(name, "empty_pk", "empty primary key", row=i, column=pk)
                    )
                elif key in seen:
                    violations.append(
                        Violation(name, "duplicate_pk",
                                  f"duplicate primary key '{key}'", row=i, column=pk)
                    )
                else:
                    seen.add(key)
        if pk:
            pk_index[name] = seen

    # foreign keys (second pass, now that parent indexes exist)
    for name in schema.order():
        spec = schema.tables[name]
        table = tables.get(name)
        if table is None:
            continue
        cols = set(table.columns)
        for fk in spec.foreign_keys:
            if fk.column not in cols:
                violations.append(
                    Violation(name, "missing_column",
                              f"foreign-key column '{fk.column}' absent")
                )
                continue
            parent_keys = pk_index.get(fk.ref_table)
            if parent_keys is None:
                # parent table's pk wasn't indexed (no pk declared / missing table)
                parent = tables.get(fk.ref_table)
                if parent is None or fk.ref_column not in parent.columns:
                    violations.append(
                        Violation(name, "broken_fk",
                                  f"cannot resolve {fk.ref_table}.{fk.ref_column}")
                    )
                    continue
                parent_keys = {r.get(fk.ref_column, "") for r in parent.rows}
            for i, row in enumerate(table.rows, start=1):
                val = row.get(fk.column, "")
                if val == "":
                    continue  # empty fk = no link; use required to forbid
                if val not in parent_keys:
                    violations.append(
                        Violation(name, "broken_fk",
                                  f"'{val}' not in {fk.ref_table}.{fk.ref_column}",
                                  row=i, column=fk.column)
                    )
    return violations


def summarize(violations: Iterable[Violation]) -> Dict[str, int]:
    """Count violations by kind."""
    counts: Dict[str, int] = {}
    for v in violations:
        counts[v.kind] = counts.get(v.kind, 0) + 1
    return counts
