import requests, json

login_res = requests.post('http://127.0.0.1:8000/auth/login', json={'email': 'admin@edip.com', 'password': 'admin123'})
tokens = login_res.json()
access_token = tokens.get('access_token', '')
headers = {'Authorization': f'Bearer {access_token}', 'Content-Type': 'application/json'}

# Test with correct connection_id=2 and dashboard mode
res = requests.post('http://127.0.0.1:8000/chat/ask', headers=headers, json={
    'connection_id': 2,
    'question': 'compare 3 months sales',
    'view_mode': 'dashboard'
})
print(f'Status: {res.status_code}')
data = res.json()
print(f'Keys: {list(data.keys())}')
print(f'Data rows: {len(data.get("data", []))}')
print(f'Summary: {str(data.get("summary", ""))[:200]}')
print(f'Chart data: {data.get("chart_data", [])}')
print(f'Error: {data.get("error", "none")}')
