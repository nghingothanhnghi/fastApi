# test_jackpot_prizes.py
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), 'app'))

from app.database import get_db
from app.jackpot.controllers.jackpot_controller import jackpot_controller
from app.jackpot.services.draw_service import draw_service
from app.jackpot.models.draw import DrawStatus
from sqlalchemy import text

def test_prizes():
    db = next(get_db())

    # Create a test user using raw SQL
    db.execute(text("INSERT INTO users (client_id, username, email, hashed_password) VALUES ('test', 'testuser', 'test@example.com', 'dummy')"))
    db.commit()
    result = db.execute(text("SELECT id FROM users WHERE username = 'testuser'"))
    user_id = result.fetchone()[0]
    print(f"Created user ID: {user_id}")

    # Create a manual draw with specific numbers and bonus
    draw = draw_service.create_draw(
        db,
        draw_type="manual",
        numbers=[1, 2, 3, 4, 5, 6],  # drawn numbers
        bonus_number=7
    )
    print(f"Created draw ID: {draw.id}, status: {draw.status}")

    # Buy tickets for different play_types with numbers that will match
    # For bao5: choose 5 numbers
    ticket_bao5 = jackpot_controller.buy_ticket(db, user_id=user_id, numbers=[1, 2, 3, 4, 5], play_type="bao5")
    print(f"Bought Bao5 ticket ID: {ticket_bao5.id}")

    # Bao7: 7 numbers
    ticket_bao7 = jackpot_controller.buy_ticket(db, user_id=user_id, numbers=[1, 2, 3, 4, 5, 6, 7], play_type="bao7")
    print(f"Bought Bao7 ticket ID: {ticket_bao7.id}")

    # Bao8: 8 numbers
    ticket_bao8 = jackpot_controller.buy_ticket(db, user_id=user_id, numbers=[1, 2, 3, 4, 5, 6, 7, 8], play_type="bao8")
    print(f"Bought Bao8 ticket ID: {ticket_bao8.id}")

    # Bao9: 9 numbers
    ticket_bao9 = jackpot_controller.buy_ticket(db, user_id=user_id, numbers=[1, 2, 3, 4, 5, 6, 7, 8, 9], play_type="bao9")
    print(f"Bought Bao9 ticket ID: {ticket_bao9.id}")

    # Complete the draw
    draw.status = DrawStatus.completed
    db.commit()
    print(f"Draw completed")

    # Check prizes
    prize_bao5 = jackpot_controller.check_ticket(db, ticket_bao5.id)
    if prize_bao5:
        print(f"Bao5 prize: category={prize_bao5.category}, value={prize_bao5.prize_value}")
    else:
        print("Bao5: No prize")

    prize_bao7 = jackpot_controller.check_ticket(db, ticket_bao7.id)
    if prize_bao7:
        print(f"Bao7 prize: category={prize_bao7.category}, value={prize_bao7.prize_value}")
    else:
        print("Bao7: No prize")

    prize_bao8 = jackpot_controller.check_ticket(db, ticket_bao8.id)
    if prize_bao8:
        print(f"Bao8 prize: category={prize_bao8.category}, value={prize_bao8.prize_value}")
    else:
        print("Bao8: No prize")

    prize_bao9 = jackpot_controller.check_ticket(db, ticket_bao9.id)
    if prize_bao9:
        print(f"Bao9 prize: category={prize_bao9.category}, value={prize_bao9.prize_value}")
    else:
        print("Bao9: No prize")

    db.close()

if __name__ == "__main__":
    test_prizes()