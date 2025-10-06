from app.database import SessionLocal
from app.jackpot.models.draw import Draw, DrawStatus

db = SessionLocal()
# Get the first draw and mark it as completed
draw = db.query(Draw).first()
if draw:
    draw.status = DrawStatus.completed
    db.commit()
    print(f"Completed draw ID: {draw.id}")
else:
    print("No draws found")
db.close()