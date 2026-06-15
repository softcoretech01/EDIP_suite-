import requests

res = requests.post('http://127.0.0.1:8000/auth/login', data={'username': 'admin@edip.com', 'password': 'admin123'})
print(f"Status Code: {res.status_code}")
print(f"Response: {res.text}")
