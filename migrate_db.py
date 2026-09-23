import sqlite3
import os

db_path = os.path.join("app", "data", "database.db")

if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()


def add_client_id_column(table_name):
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]

    if "client_id" in columns:
        print(f"{table_name}: client_id already exists")
        return

    cursor.execute(
        f"ALTER TABLE {table_name} ADD COLUMN client_id TEXT"
    )

    print(f"{table_name}: client_id added")


def add_client_id_index(table_name):
    index_name = f"ix_{table_name}_client_id"

    cursor.execute(
        f"""
        CREATE INDEX IF NOT EXISTS {index_name}
        ON {table_name} (client_id)
        """
    )

    print(f"{table_name}: client_id index ready")


def add_rain_raw_column():
    table_name = "sensor_data"

    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]

    if "rain_raw" in columns:
        print(f"{table_name}: rain_raw already exists")
        return

    cursor.execute(
        f"ALTER TABLE {table_name} ADD COLUMN rain_raw INTEGER"
    )

    print(f"{table_name}: rain_raw added")

try:
    # Add missing client_id columns
    add_client_id_column("ai_vision_cameras")
    add_client_id_column("ai_vision_plants")

    # Match SQLAlchemy index=True
    add_client_id_index("ai_vision_cameras")
    add_client_id_index("ai_vision_plants")

    # Add rain_raw to sensor_data
    add_rain_raw_column()

    conn.commit()

    print("\nMigration completed successfully.")

except sqlite3.Error as e:
    conn.rollback()
    print(f"Database error: {e}")

finally:
    conn.close()