# migrate_recipe_targets.py
# Idempotent: adds group_name / actuator_id for recipe targeting.
import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text
from app.database import engine


def backup_sqlite() -> None:
    if engine.url.get_backend_name() != "sqlite":
        print("Non-SQLite DB: take your own backup first.")
        return
    db_file = engine.url.database
    if db_file and os.path.exists(db_file):
        backup = f"{db_file}.bak_{datetime.now():%Y%m%d_%H%M%S}"
        shutil.copy2(db_file, backup)
        print(f"Backup written: {backup}")


def has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(engine).get_columns(table)]


def add_column(conn, table: str, column: str, ddl: str) -> None:
    if has_column(table, column):
        print(f"{table}.{column}: already exists")
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {ddl}"))
    print(f"{table}.{column}: added")


def main() -> None:
    backup_sqlite()
    with engine.begin() as conn:
        add_column(conn, "hydro_actuators", "group_name", "VARCHAR(50)")
        add_column(conn, "growth_recipes", "group_name", "VARCHAR(50)")
        add_column(conn, "growth_recipes", "actuator_id",
                   "INTEGER REFERENCES hydro_actuators(id)")
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_hydro_actuators_group_name "
            "ON hydro_actuators (group_name)"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_growth_recipes_actuator_id "
            "ON growth_recipes (actuator_id)"))
    print("Migration completed.")


if __name__ == "__main__":
    main()