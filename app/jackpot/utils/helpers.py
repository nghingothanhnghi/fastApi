# app/jackpot/utils/helpers.py

import random
from itertools import combinations
from math import comb
from datetime import datetime, timedelta
import calendar

def generate_draw_numbers():
    numbers = random.sample(range(1, 56), 6)
    bonus_pool = [n for n in range(1, 56) if n not in numbers]
    bonus_number = random.choice(bonus_pool)
    return sorted(numbers), bonus_number

def count_matches(ticket_numbers, draw_numbers):
    return len(set(ticket_numbers) & set(draw_numbers))

def generate_combinations(numbers, pick=6):
    return list(combinations(numbers, pick))


def calculate_jackpot_probabilities(n: int = 55, k: int = 6, bonus: bool = True):
    """
    Tính xác suất trúng thưởng cho Jackpot.
    
    Args:
        n (int): Tổng số bóng (ví dụ 55)
        k (int): Số bóng chọn (ví dụ 6)
        bonus (bool): Có rút số Bonus hay không (True/False)
    
    Returns:
        dict: Xác suất cho Jackpot, 5+Bonus, 4 số, 3 số
    """
    total_combinations = comb(n, k)
    probabilities = {
        "jackpot": 1 / total_combinations
    }

    if bonus:
        # 5 + Bonus: Chọn đúng 5 số, và số còn lại phải là Bonus
        # Chọn 5 số đúng trong 6 và 1 số Bonus trong n-k
        p_5_plus_bonus = (comb(k, 5) * (n - k)) / total_combinations / (n - k)
        probabilities["five_plus_bonus"] = p_5_plus_bonus

    # 4 số
    p_4_numbers = (comb(k, 4) * comb(n - k, k - 4)) / total_combinations
    probabilities["four_numbers"] = p_4_numbers

    # 3 số
    p_3_numbers = (comb(k, 3) * comb(n - k, k - 3)) / total_combinations
    probabilities["three_numbers"] = p_3_numbers

    return probabilities

# --- NEW CODE for draw scheduling ---
def get_next_draw_date(base_time: datetime, draw_days: list[str], draw_time: str) -> datetime:
    """
    Find the next scheduled draw datetime strictly after base_time.
    draw_days: ["Tuesday", "Thursday", "Saturday"]
    draw_time: "18:00"
    """
    hour, minute = map(int, draw_time.split(":"))
    base_time = base_time.replace(second=0, microsecond=0)

    for i in range(1, 8):  # 🔑 start from +1 day to avoid repeating same-day draw
        candidate = base_time + timedelta(days=i)
        weekday_name = calendar.day_name[candidate.weekday()]
        if weekday_name in draw_days:
            candidate = candidate.replace(hour=hour, minute=minute)
            if candidate > base_time:
                return candidate

    raise RuntimeError("No valid draw day found in rules!")
