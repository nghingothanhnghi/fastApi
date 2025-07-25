# app/transform_data/servicesai_mapper.py
# This module provides AI-based mapping of raw data fields to standard business fields using OpenAI's API.
from openai import OpenAI
from app.core.config import OPENAI_API_KEY, USE_MOCK_AI
import json

SYSTEM_PROMPT = (
    "You're a data integration assistant. Your job is to help map raw data fields to standard business fields. "
    "Given a JSON object, suggest a mapping from standard business fields to the raw field names. "
    "Return a JSON in the form:\n{\n  \"standard_field\": \"raw_field\"\n}"
)

# ✅ initialize OpenAI client
client = OpenAI(api_key=OPENAI_API_KEY)

def generate_mapping_prompt(raw_data: dict, client_id: str) -> str:
    return f"""
Client ID: {client_id}

Given the following raw JSON payload:

{json.dumps(raw_data, indent=2)}

Suggest a mapping to standard business field names.
Return a JSON like:
{{
  "standard_field": "raw_field"
}}
"""

async def suggest_mapping(raw_data: dict, client_id: str) -> dict:

    if USE_MOCK_AI:
        return {
            "name": "full_name",
            "email": "email_address",
            "phone": "contact_number",
            "address": "location_field"
        }

    prompt = generate_mapping_prompt(raw_data, client_id)

    try:
        # ✅ Use new Assistants-like response API
        response = await client.responses.create(
            model="gpt-4o-mini",  # or "gpt-4o"
            input=prompt,
            store=False  # or True if you want it saved to thread history
        )

        reply = response.output_text

        try:
            mapping = json.loads(reply)
        except json.JSONDecodeError:
            mapping = {"error": "Invalid JSON response from AI", "raw": reply}

        return mapping

    except Exception as e:
        return {"error": "AI mapping failed", "details": str(e)}
