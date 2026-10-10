import requests

API_URL = "http://localhost:5173"  # Replace with your actual URL
TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTc1MzY3NTc1M30.2_OJDl4lHrphR3eVMD68OurKW1T5Yixk3ETs2_kMNQo"      # Replace with your real JWT token (from login)

headers = {
    "Authorization": f"Bearer {TOKEN}"
}

def fetch_hydro_status():
    try:
        response = requests.get(f"{API_URL}/hydro/status", headers=headers)
        response.raise_for_status()

        data = response.json()
        print("✅ Hydro System Status:")
        print(data)

    except requests.exceptions.HTTPError as http_err:
        print(f"❌ HTTP error occurred: {http_err}")
        if response.content:
            print("Details:", response.json())
    except Exception as err:
        print(f"❌ Other error occurred: {err}")

if __name__ == "__main__":
    fetch_hydro_status()
