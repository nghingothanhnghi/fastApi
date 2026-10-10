import requests

API_URL = "http://localhost:8000/hydro/devices"  # Replace with actual base URL
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTc1MzY3NTc1M30.2_OJDl4lHrphR3eVMD68OurKW1T5Yixk3ETs2_kMNQo"        # Replace with real token

headers = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json"
}

device_data = {
    "name": "Test ESP32",
    "device_id": "esp32_dev_001",
    "location": "Lab A",
    "type": "ESP32",
    "is_active": True,
    "client_id": "esp32_1",
    "thresholds": {},     # or put default thresholds like {"temperature": {"min": 20, "max": 35}}
    "user_id": 1
}

response = requests.post(API_URL, headers=headers, json=device_data)

print("Status Code:", response.status_code)
print("Response:", response.json())
