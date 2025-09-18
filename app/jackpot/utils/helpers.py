import random
from itertools import combinations

def generate_draw_numbers():
    numbers = random.sample(range(1, 56), 6)
    bonus_pool = [n for n in range(1, 56) if n not in numbers]
    bonus_number = random.choice(bonus_pool)
    return sorted(numbers), bonus_number

def count_matches(ticket_numbers, draw_numbers):
    return len(set(ticket_numbers) & set(draw_numbers))

def generate_combinations(numbers, pick=6):
    return list(combinations(numbers, pick))
