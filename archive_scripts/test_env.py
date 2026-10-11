import urllib.request
import json
import urllib.error
try:
    req = urllib.request.Request('http://127.0.0.1:5000/api/projects')
    response = urllib.request.urlopen(req)
    print("Server is running.")
except urllib.error.URLError as e:
    print(f"Error: {e}")
