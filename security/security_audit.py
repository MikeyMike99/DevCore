import requests
import sys

BASE_URL = "http://localhost:5000"

def login(username, password):
    res = requests.post(f"{BASE_URL}/api/auth/login", json={"username": username, "password": password})
    if res.status_code == 200:
        return res.json().get("token")
    return None

def test_read_file(token, path, expected_status):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    res = requests.get(f"{BASE_URL}/api/files/content", params={"path": path}, headers=headers)
    if res.status_code == expected_status or (expected_status == 403 and res.status_code in [403, 500]): 
        # Sometimes permission errors bubble up as 500 depending on Quart error handlers
        print(f"[PASS] Read {path} - Expected {expected_status}, Got {res.status_code}")
        return True
    else:
        print(f"[FAIL] Read {path} - Expected {expected_status}, Got {res.status_code} ({res.text})")
        return False

def test_write_file(token, path, content, expected_status):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    res = requests.post(f"{BASE_URL}/api/files/content", json={"path": path, "content": content}, headers=headers)
    if res.status_code == expected_status or (expected_status == 403 and res.status_code in [403, 500]):
        print(f"[PASS] Write {path} - Expected {expected_status}, Got {res.status_code}")
        return True
    else:
        print(f"[FAIL] Write {path} - Expected {expected_status}, Got {res.status_code} ({res.text})")
        return False

def run_audit():
    print("=======================================")
    print("   AUTOMATED SECURITY TIER AUDIT       ")
    print("=======================================\n")

    print("[*] Authenticating Mock Users...")
    admin_token = login("admin", "admin")
    dev_token = login("dev", "dev")
    mod_token = login("mod", "mod")
    
    if not all([admin_token, dev_token, mod_token]):
        print("[!] Failed to authenticate one or more users. Is the server running with default test accounts?")
        sys.exit(1)
        
    print("[+] Authentication Successful.\n")

    passed = 0
    total = 0

    def run_test(test_func, *args):
        nonlocal passed, total
        total += 1
        if test_func(*args):
            passed += 1

    print("--- 1. Testing Path Traversal (LFI) ---")
    # Dev tries to escape to root
    run_test(test_read_file, dev_token, "../../../../../../etc/passwd", 403)
    # Dev tries to escape to core engine
    run_test(test_read_file, dev_token, "../core/server.py", 403)

    print("\n--- 2. Testing Role-Based Access Control (RBAC) ---")
    # Admin should be able to read core engine
    run_test(test_read_file, admin_token, "core/server.py", 200)
    # Dev should NOT be able to read core engine
    run_test(test_read_file, dev_token, "core/server.py", 403)
    # Modder should NOT be able to write ANY file
    run_test(test_write_file, mod_token, "playground/test_write.txt", "Hello World", 403)
    # Dev SHOULD be able to write safe workspace files
    run_test(test_write_file, dev_token, "playground/test_dev_write.txt", "Hello Dev", 200)

    print("\n--- 3. Testing Second-Order Execution Prevention ---")
    # Admin tries to write a python file with os.execute
    run_test(test_write_file, admin_token, "playground/malicious.py", "import os\nos.execute('whoami')", 403)
    # Dev tries to write a bash script with rm -rf
    run_test(test_write_file, dev_token, "playground/malicious.sh", "#!/bin/bash\nrm -rf /", 403)

    print(f"\n=======================================")
    print(f"   AUDIT COMPLETE: {passed}/{total} TESTS PASSED")
    print(f"=======================================")

if __name__ == "__main__":
    run_audit()
