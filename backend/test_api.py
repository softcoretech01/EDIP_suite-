import requests
import json

BASE_URL = "http://localhost:8000"

# 1. Login
login_res = requests.post(f"{BASE_URL}/auth/login", json={
    "email": "admin@edip.com",
    "password": "admin123"
})
print("Login Status:", login_res.status_code)
import requests
import json

BASE_URL = "http://localhost:8000"

# 1. Login
login_res = requests.post(f"{BASE_URL}/auth/login", json={
    "email": "admin@edip.com",
    "password": "admin123"
})
print("Login Status:", login_res.status_code)
tokens = login_res.json()
access_token = tokens["access_token"]

# 2. Ask a query with INTERVAL 1 MONTH date filter
headers = {"Authorization": f"Bearer {access_token}"}
response = requests.post(f"{BASE_URL}/chat/ask", json={
    "connection_id": 4,
    "question": "how many sales this month",
    "view_mode": "dashboard"
}, headers=headers)

print("Ask Status:", response.status_code)
print("Response:")
print(json.dumps(response.json(), indent=2))
