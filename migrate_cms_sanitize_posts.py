# migrate_cms_sanitize_posts.py
# Idempotent: re-sanitizes the HTML `content` of every existing CMS post/page.
# Run once after deploying write-time sanitization:  python migrate_cms_sanitize_posts.py
import os
import shutil
from datetime import datetime

from app.database import engine, SessionLocal
import app.init_db  # noqa: F401  (registers every model)
from app.cms.services.post_service import post_service


def backup_sqlite() -> None:
    if engine.url.get_backend_name() != "sqlite":
        print("Non-SQLite DB: take your own backup first.")
        return
    db_file = engine.url.database
    if db_file and os.path.exists(db_file):
        backup = f"{db_file}.bak_{datetime.now():%Y%m%d_%H%M%S}"
        shutil.copy2(db_file, backup)
        print(f"Backup written: {backup}")


def main() -> None:
    backup_sqlite()
    db = SessionLocal()
    try:
        changed = post_service.sanitize_all_posts(db)
        print(f"cms_posts: {changed} post(s) sanitized")
    finally:
        db.close()


if __name__ == "__main__":
    main()
