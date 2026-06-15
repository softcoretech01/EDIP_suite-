import requests
import json

payload = {
    "connection_id": 2,
    "question": "Python Code: Printing 'Hello Kabilesh'",
    "view_mode": "chat",
    "session_id": "test-session"
}
try:
    response = requests.post("http://localhost:8001/chat/ask", json=payload, timeout=60)
    print("STATUS CODE:", response.status_code)
    if response.status_code == 200:
        print("RESPONSE:")
        print(response.json().get("summary"))
    else:
        print("ERROR:", response.text)
except Exception as e:
    print("ERROR:", e)
