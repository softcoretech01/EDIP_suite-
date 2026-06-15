import requests
import time

BASE_URL = "http://localhost:8001"

def test_unauthorized_access():
    print("\n--- Test 1: Unauthorized Access ---")
    res = requests.post(f"{BASE_URL}/chat/ask", json={
        "connection_id": 2,
        "question": "show me top 5 items"
    })
    print(f"Status Code (Expected 401): {res.status_code}")
    assert res.status_code == 401
    print("Success: Unauthorized access blocked.")

def test_login_and_profile():
    print("\n--- Test 2: Login and Profile Fetch ---")
    # Login as Admin
    login_res = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "admin@edip.com",
        "password": "admin123"
    })
    print(f"Login Status (Expected 200): {login_res.status_code}")
    assert login_res.status_code == 200
    
    tokens = login_res.json()
    assert "access_token" in tokens
    assert "refresh_token" in tokens
    print("Tokens retrieved successfully.")
    
    # Get Profile
    headers = {"Authorization": f"Bearer {tokens['access_token']}"}
    me_res = requests.get(f"{BASE_URL}/auth/me", headers=headers)
    print(f"Profile Status (Expected 200): {me_res.status_code}")
    assert me_res.status_code == 200
    
    profile = me_res.json()
    print(f"Logged in user email: {profile['email']}")
    print(f"Assigned roles: {profile['roles']}")
    assert profile['email'] == "admin@edip.com"
    assert "Administrator" in profile['roles']
    return tokens

def test_rbac_controls(admin_tokens):
    print("\n--- Test 3: Role-Based Access Control ---")
    
    # Login as Dev (Manager)
    dev_login = requests.post(f"{BASE_URL}/auth/login", json={
        "email": "dev@edip.com",
        "password": "password123"
    })
    assert dev_login.status_code == 200
    dev_tokens = dev_login.json()
    
    # 1. Admin should access debug-qdrant (requires admin_settings)
    admin_headers = {"Authorization": f"Bearer {admin_tokens['access_token']}"}
    admin_debug = requests.get(f"{BASE_URL}/chat/debug-qdrant", headers=admin_headers)
    print(f"Admin debug-qdrant Access (Expected 200): {admin_debug.status_code}")
    assert admin_debug.status_code == 200
    
    # 2. Dev (Manager) should NOT access debug-qdrant
    dev_headers = {"Authorization": f"Bearer {dev_tokens['access_token']}"}
    dev_debug = requests.get(f"{BASE_URL}/chat/debug-qdrant", headers=dev_headers)
    print(f"Dev debug-qdrant Access (Expected 403): {dev_debug.status_code}")
    assert dev_debug.status_code == 403
    print("Success: RBAC limits verified.")

def test_token_refresh(admin_tokens):
    print("\n--- Test 4: Token Refresh Cycles ---")
    refresh_res = requests.post(f"{BASE_URL}/auth/refresh", json={
        "refresh_token": admin_tokens["refresh_token"]
    })
    print(f"Refresh Status (Expected 200): {refresh_res.status_code}")
    assert refresh_res.status_code == 200
    
    new_tokens = refresh_res.json()
    assert "access_token" in new_tokens
    print("Success: Access token refreshed successfully.")

def test_user_registration():
    print("\n--- Test 5: User Registration and Tenant Isolation ---")
    test_email = f"user_{int(time.time())}@edip.com"
    
    # Register new user
    reg_res = requests.post(f"{BASE_URL}/auth/register", json={
        "email": test_email,
        "password": "userpass123",
        "full_name": "Test Isolated User",
        "tenant_name": "Isolated Corp"
    })
    print(f"Registration Status (Expected 201): {reg_res.status_code}")
    assert reg_res.status_code == 201
    
    reg_data = reg_res.json()
    print(f"New User ID: {reg_data['id']}, Tenant ID: {reg_data['tenant_id']}")
    assert reg_data['email'] == test_email
    assert "Manager" in reg_data['roles']
    
    # Login as the new isolated user
    login_res = requests.post(f"{BASE_URL}/auth/login", json={
        "email": test_email,
        "password": "userpass123"
    })
    assert login_res.status_code == 200
    new_tokens = login_res.json()
    
    # Try querying connection 2 (which belongs to tenant 1)
    new_headers = {"Authorization": f"Bearer {new_tokens['access_token']}"}
    query_res = requests.post(f"{BASE_URL}/chat/ask", json={
        "connection_id": 2, # Belongs to tenant 1
        "question": "show me total sales"
    }, headers=new_headers)
    
    print(f"Cross-Tenant Query status (Expected 403): {query_res.status_code}")
    assert query_res.status_code == 403
    print("Success: Cross-tenant connection access blocked.")

def main():
    print("Starting Automated Security & Auth Test Suite...")
    try:
        test_unauthorized_access()
        admin_tokens = test_login_and_profile()
        test_rbac_controls(admin_tokens)
        test_token_refresh(admin_tokens)
        test_user_registration()
        print("\nALL SECURITY TESTS PASSED SUCCESSFULLY! (OK)")
    except AssertionError as e:
        print(f"\nAssertion Error: Test validation failed. (FAIL)")
        raise e
    except Exception as e:
        print(f"\nUnexpected error during test execution: {e} (FAIL)")
        raise e

if __name__ == "__main__":
    main()
