"""Tiny, ordered schema-migration runner.

``create_all`` builds fresh databases. Each entry below upgrades an older database
in place; applied versions are recorded in ``schema_version`` so they run once.
Swap in Alembic when the schema starts changing often.
"""

from __future__ import annotations

from sqlalchemy import Engine, inspect, text

# (version, description, list of SQL statements, guard(inspector) -> needs_apply)
MIGRATIONS: list[tuple[int, str, list[str]]] = [
    (1, "baseline", []),
    (2, "clip feedback note", ["ALTER TABLE clips ADD COLUMN feedback_note TEXT"]),
    (3, "clip post/schedule plan", ["ALTER TABLE clips ADD COLUMN post JSON DEFAULT '{}'"]),
]


def apply(engine: Engine) -> None:
    with engine.begin() as conn:
        conn.execute(text("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"))
        done = {r[0] for r in conn.execute(text("SELECT version FROM schema_version"))}
        cols = {c["name"] for c in inspect(conn).get_columns("clips")}
        for version, _desc, statements in MIGRATIONS:
            if version in done:
                continue
            for stmt in statements:
                # Skip ADD COLUMN when create_all already produced the column.
                if "ADD COLUMN" in stmt:
                    col = stmt.split("ADD COLUMN")[1].split()[0]
                    if col in cols:
                        continue
                conn.execute(text(stmt))
            conn.execute(text("INSERT INTO schema_version (version) VALUES (:v)"), {"v": version})
