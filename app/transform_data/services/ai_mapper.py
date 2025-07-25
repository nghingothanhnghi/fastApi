# app/transform_data/servicesai_mapper.py
# This module provides AI-based mapping of raw data fields to standard business fields using OpenAI's API.
from openai import OpenAI
from app.core.config import OPENAI_API_KEY
import json

SYSTEM_PROMPT = (
    "You're a data integration assistant. Your job is to help map raw data fields to standard business fields."
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
    prompt = generate_mapping_prompt(raw_data, client_id)

    # ✅ use new SDK method
    response = await client.chat.completions.create(
        model="gpt-4",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ],
        temperature=0.3,
    )

    reply = response.choices[0].message.content

    try:
        mapping = json.loads(reply)
    except json.JSONDecodeError:
        mapping = {"error": "Invalid response from AI", "raw": reply}

    return mapping
