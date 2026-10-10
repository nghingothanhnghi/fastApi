#!/usr/bin/env python3
"""
Test script for the Data Transformation System
Run this after starting your FastAPI server to test the transformation flow
"""

import requests
import json
import time

BASE_URL = "http://localhost:8000"

def test_transformation_system():
    print("🚀 Testing Data Transformation System")
    print("=" * 50)
    
    # Step 1: Create a template
    print("\n1️⃣ Creating transformation template...")
    template_data = {
        "client_id": "test_client_123",
        "mapping": {
            "customer_name": "user_name",
            "customer_email": "user_email", 
            "order_amount": "total_price",
            "item_count": "quantity"
        }
    }
    
    try:
        response = requests.post(f"{BASE_URL}/templates", json=template_data)
        if response.status_code == 200:
            print("✅ Template created successfully!")
            print(f"   Template: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"❌ Failed to create template: {response.status_code}")
            print(f"   Error: {response.text}")
            return
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")
        return
    
    # Step 2: Post raw data
    print("\n2️⃣ Posting raw data...")
    raw_data = {
        "client_id": "test_client_123",
        "payload": {
            "user_name": "John Doe",
            "user_email": "john.doe@example.com",
            "total_price": 299.99,
            "quantity": 5,
            "order_date": "2024-01-15",
            "extra_field": "this will be ignored"
        }
    }
    
    try:
        response = requests.post(f"{BASE_URL}/ingest", json=raw_data)
        if response.status_code == 200:
            print("✅ Raw data posted successfully!")
            print(f"   Response: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"❌ Failed to post data: {response.status_code}")
            print(f"   Error: {response.text}")
            return
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")
        return
    
    # Step 3: Test manual transformation
    print("\n3️⃣ Testing manual transformation...")
    transform_request = {
        "client_id": "test_client_123",
        "raw_data": {
            "user_name": "Jane Smith",
            "user_email": "jane@example.com",
            "total_price": 150.50,
            "quantity": 2
        }
    }
    
    try:
        response = requests.post(f"{BASE_URL}/transform", json=transform_request)
        if response.status_code == 200:
            print("✅ Manual transformation successful!")
            print(f"   Transformed data: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"❌ Transformation failed: {response.status_code}")
            print(f"   Error: {response.text}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")
    
    # Step 4: Check template
    print("\n4️⃣ Retrieving template...")
    try:
        response = requests.get(f"{BASE_URL}/templates/test_client_123")
        if response.status_code == 200:
            print("✅ Template retrieved successfully!")
            print(f"   Template: {json.dumps(response.json(), indent=2)}")
        else:
            print(f"❌ Failed to get template: {response.status_code}")
    except requests.exceptions.RequestException as e:
        print(f"❌ Connection error: {e}")
    
    print("\n" + "=" * 50)
    print("🎉 Test completed!")
    print("💡 The background job will process the ingested data within 10 seconds")
    print("📝 Check your server logs to see the automatic transformation")

if __name__ == "__main__":
    test_transformation_system()