import requests
res = requests.post('http://127.0.0.1:5000/api/artifacts/save', json={'path': 'client_debug.txt', 'content': 'test log\n', 'append': True})
print(res.status_code, res.text)
