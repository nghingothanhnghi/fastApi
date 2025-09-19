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

rule_service = RuleService()
