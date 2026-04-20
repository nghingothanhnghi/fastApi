import sqlite3
import os

db_path = os.path.join('app', 'data', 'database.db')
if not os.path.exists(db_path):
    print(f"Database not found at {db_path}")
    exit(1)

conn = sqlite3.connect(db_path)
cursor = conn.cursor()

cursor.execute('SELECT * FROM sensor_data WHERE device_id = 1 ORDER BY created_at DESC LIMIT 5')
data = cursor.fetchall()
for row in data:
    print(row)

conn.close()
