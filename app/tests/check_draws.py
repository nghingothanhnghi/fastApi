from app.database import SessionLocal
from app.jackpot.models.draw import Draw

db = SessionLocal()
draws = db.query(Draw).all()
print(f'Total draws: {len(draws)}')
for d in draws:
    print(f'ID: {d.id}, Date: {d.draw_date}, Status: {d.status}, Numbers: {d.numbers}')
db.close()