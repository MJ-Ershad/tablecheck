"""tablecheck: validate referential integrity across related CSV/TSV tables.

A dependency-free toolkit for checking that a set of flat tabular files
(CSV or TSV) are internally consistent: primary keys are unique and present,
foreign keys resolve to an existing parent row, required columns exist, and
declared column types parse. The schema is a small JSON document, so the same
checks run in CI without a database.
"""

from .core import (
    Schema,
    Table,
    Violation,
    load_schema,
    read_table,
    validate,
)

__all__ = [
    "Schema",
    "Table",
    "Violation",
    "load_schema",
    "read_table",
    "validate",
]

__version__ = "0.1.0"
