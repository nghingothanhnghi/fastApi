# migrate_growth_plans.py
# One-off, idempotent migration for multi-plan support.
#
#   python migrate_growth_plans.py
#
# Works on SQLite and PostgreSQL (uses the app's engine / DATABASE_URL).
#
# What it does:
#   1. (SQLite only) backs up the DB file
#   2. creates growth_plans if missing
#   3. adds growth_stages.plan_id and plant_batches.plan_id if missing
#   4. creates a "Default Plan" for every plant that has no plan
#   5. makes sure every plant with plans has a default plan
#   6. backfills plan_id on existing stages and batches from the plant's default plan
#   7. reports rows still missing plan_id (should be 0)

import os
import shutil
from datetime import datetime

from sqlalchemy import inspect, text

from app.database import engine
from app.hydro_system.models.growth_plan import GrowthPlan
# Importing these makes sure their tables are registered / exist.
from app.hydro_system.models.plant import Plant  # noqa: F401
from app.hydro_system.models.growth_stage import GrowthStage  # noqa: F401
from app.hydro_system.models.plant_batch import PlantBatch  # noqa: F401


def backup_sqlite() -> None:
    if engine.url.get_backend_name() != "sqlite":
        print("Non-SQLite database: take a DB backup/snapshot yourself before continuing.")
        return
    db_file = engine.url.database
    if not db_file or not os.path.exists(db_file):
        print(f"SQLite file not found ({db_file}); skipping backup.")
        return
    backup = f"{db_file}.bak_{datetime.now():%Y%m%d_%H%M%S}"
    shutil.copy2(db_file, backup)
    print(f"Backup written: {backup}")


def has_column(table: str, column: str) -> bool:
    return column in [c["name"] for c in inspect(engine).get_columns(table)]


def add_plan_id_column(conn, table: str) -> None:
    if has_column(table, "plan_id"):
        print(f"{table}: plan_id already exists")
        return
    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN plan_id INTEGER REFERENCES growth_plans(id)"))
    print(f"{table}: plan_id added")


def main() -> None:
    backup_sqlite()

    # 1) growth_plans table (checkfirst => no-op if init_db() already made it)
    GrowthPlan.__table__.create(bind=engine, checkfirst=True)
    print("growth_plans: table ready")

    with engine.begin() as conn:
        # 2) new columns
        add_plan_id_column(conn, "growth_stages")
        add_plan_id_column(conn, "plant_batches")

        # 3) a default plan for every plant that has none
        created = conn.execute(
            text(
                """
                INSERT INTO growth_plans (plant_id, name, description, is_default)
                SELECT p.id, 'Default Plan', 'Auto-created by multi-plan migration', :yes
                FROM plants p
                WHERE NOT EXISTS (SELECT 1 FROM growth_plans gp WHERE gp.plant_id = p.id)
                """
            ),
            {"yes": True},
        ).rowcount
        print(f"growth_plans: {created} default plan(s) created")

        # 4) plants that have plans but no default -> promote the earliest
        promoted = conn.execute(
            text(
                """
                UPDATE growth_plans SET is_default = :yes
                WHERE id IN (
                    SELECT MIN(id) FROM growth_plans
                    GROUP BY plant_id
                    HAVING SUM(CASE WHEN is_default THEN 1 ELSE 0 END) = 0
                )
                """
            ),
            {"yes": True},
        ).rowcount
        print(f"growth_plans: {promoted} plant(s) had no default, earliest plan promoted")

        # 5) backfill stages and batches from the plant's default plan
        stages = conn.execute(
            text(
                """
                UPDATE growth_stages
                SET plan_id = (
                    SELECT gp.id FROM growth_plans gp
                    WHERE gp.plant_id = growth_stages.plant_id AND gp.is_default = :yes
                    ORDER BY gp.id LIMIT 1
                )
                WHERE plan_id IS NULL AND plant_id IS NOT NULL
                """
            ),
            {"yes": True},
        ).rowcount
        batches = conn.execute(
            text(
                """
                UPDATE plant_batches
                SET plan_id = (
                    SELECT gp.id FROM growth_plans gp
                    WHERE gp.plant_id = plant_batches.plant_id AND gp.is_default = :yes
                    ORDER BY gp.id LIMIT 1
                )
                WHERE plan_id IS NULL AND plant_id IS NOT NULL
                """
            ),
            {"yes": True},
        ).rowcount
        print(f"growth_stages: {stages} row(s) backfilled")
        print(f"plant_batches: {batches} row(s) backfilled")

        # 6) verification
        for table in ("growth_stages", "plant_batches"):
            remaining = conn.execute(
                text(f"SELECT COUNT(*) FROM {table} WHERE plan_id IS NULL")
            ).scalar()
            flag = "OK" if remaining == 0 else "CHECK: rows with no plant_id/plan"
            print(f"{table}: {remaining} row(s) with plan_id NULL  [{flag}]")

    print("\nMigration completed.")


if __name__ == "__main__":
    main()
