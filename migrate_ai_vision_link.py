# migrate_ai_vision_link.py
#   python migrate_ai_vision_link.py            # apply
#   python migrate_ai_vision_link.py --dry-run  # report only
import sys

# IMPORTANT: importing init_db registers EVERY model with SQLAlchemy
# (GrowthPlan, PlantBatch, User, ...). Without it, string relationships such
# as relationship("GrowthPlan") cannot be resolved in a standalone script.
import app.init_db  # noqa: F401

from app.database import SessionLocal
from app.ai_vision.models.plant import VisionPlant
from app.ai_vision.integrations.hydro_batch_client import hydro_batch_client


def main(dry_run: bool) -> None:
    db = SessionLocal()
    fixed = {"location": 0, "hydro_plant_id": 0, "client_id": 0, "orphan_batch": 0}
    try:
        plants = db.query(VisionPlant).filter(VisionPlant.hydro_batch_id.isnot(None)).all()
        print(f"Found {len(plants)} batch-linked vision plant(s)")

        for p in plants:
            info = hydro_batch_client.get_batch_with_plant(db, p.hydro_batch_id)
            if not info:
                fixed["orphan_batch"] += 1
                print(f"plant {p.id}: hydro batch {p.hydro_batch_id} no longer exists")
                continue
            if not p.location and info["zone_location"]:
                p.location = info["zone_location"]
                fixed["location"] += 1
            if p.hydro_plant_id != info["plant_id"]:
                p.hydro_plant_id = info["plant_id"]
                fixed["hydro_plant_id"] += 1
            if p.client_id is None and info["zone_client_id"]:
                p.client_id = info["zone_client_id"]
                fixed["client_id"] += 1

        if dry_run:
            db.rollback()
        else:
            db.commit()
        print(("DRY RUN - " if dry_run else "") + f"done: {fixed}")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main("--dry-run" in sys.argv)