import requests

# Test the latest draw API
url = "http://localhost:8000/jackpot/draw/latest"
response = requests.get(url)

if response.status_code == 200:
    data = response.json()
    print("API Response:")
    print(f"Draw ID: {data['id']}")
    print(f"Draw Date: {data['draw_date']}")
    print(f"Status: {data['status']}")
    print(f"Numbers: {data['numbers']}")
    print(f"Bonus Number: {data['bonus_number']}")
else:
    print(f"Error: {response.status_code} - {response.text}")