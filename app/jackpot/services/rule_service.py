# app/jackpot/services/rule_service.py
class RuleService:
    def get_rules(self):
        return {
            "min_price": 10000,
            "number_range": list(range(1, 56)),
            "jackpot1_min": 30000000000,
            "jackpot2_min": 3000000000,
            "draw_days": ["Tuesday", "Thursday", "Saturday"],
            "draw_time": "18:00",
        }

    def get_prize_tables(self):
        return {
            # ✅ Basic play type (normal rules)
            "basic": {
                (3, False): 100000,  # example payouts, adjust to your official rules
                (4, False): 500000,
                (5, False): 10000000,
                (5, True): lambda jackpot2: jackpot2,  # Jackpot2
                (6, False): lambda jackpot1: jackpot1, # Jackpot1
            },            
            "bao5": {
                (2, False): 200000,
                (3, False): 3850000,
                (4, False): 104000000,
                (4, True): lambda jackpot2: (jackpot2 * 2) + 24000000,
                (5, False): lambda jackpot1, jackpot2: jackpot1 + jackpot2 + 1920000000000,
            },
            "bao7": {
                (3, False): 200000,
                (4, False): 1700000,
                (5, False): 82500000,
                (5, True): lambda jackpot2: jackpot2 + 42500000,
                (6, False): lambda jackpot1: jackpot1 + 240000000,
                (6, True): lambda jackpot1, jackpot2: jackpot1 + jackpot2,
            },
            "bao8": {
                (3, False): 500000,
                (4, False): 3800000,
                (5, False): 128000000,
                (5, True): lambda jackpot2: jackpot2 + 88000000,
                (6, False): lambda jackpot1: jackpot1 + 487500000,
                (6, True): lambda jackpot1, jackpot2: jackpot1 + jackpot2 + 247500000,
            },
            "bao9": {
                (3, False): 1000000,
                (4, False): 7000000,
                (5, False): 177000000,
                (5, True): lambda jackpot2: jackpot2 + 137000000,
                (6, False): lambda jackpot1: jackpot1 + 743500000,
                (6, True): lambda jackpot1, jackpot2: jackpot1 + jackpot2 + 503500000,
            },
        }

rule_service = RuleService()
