import urllib.request
import json
data = json.dumps({"path": "/mnt/c/Users/michael/Documents/devcore/sandbox/templates/client_debug.txt", "content": "Test Log"})
req = urllib.request.Request("http://127.0.0.1:5000/api/artifacts/save", data=data.encode('utf-8'), headers={'Content-Type': 'application/json'}, method='POST')
try:
    with urllib.request.urlopen(req) as response:
        print(response.read().decode())
except Exception as e:
    print("Error:", e)
