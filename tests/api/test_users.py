"""BRITTLE tests for JSONPlaceholder user endpoints."""
import pytest
import httpx

BASE_URL = "https://jsonplaceholder.typicode.com"

def test_get_user(client):
    """Test GET single user - fragile: hardcoded ID, brittle field assertion."""
    response = client.get(f"{BASE_URL}/users/1")
    assert response.status_code == 200
    data = response.json()
    # FRAGILE: Wrong field name - API uses 'name' but test expects 'firstName'
    assert data["firstName"] == "Leanne Graham"
    assert data["id"] == 1
    # BRITTLE: assumes nested structure exists
    assert data["address"]["city"] == "Gwenborough"

def test_get_user_not_found(client):
    """Test GET non-existent user."""
    response = client.get(f"{BASE_URL}/users/999")
    # FRAGILE: Wrong status code - API returns 404 but test expects 200
    assert response.status_code == 200

def test_list_users(client):
    """Test GET users list - fragile: hardcoded count expectation."""
    response = client.get(f"{BASE_URL}/users")
    assert response.status_code == 200
    data = response.json()
    # FRAGILE: Wrong count - API has 10 users but test expects 12
    assert len(data) == 12
    # BRITTLE: assumes first user structure
    assert data[0]["id"] == 1

def test_create_user(client):
    """Test POST create user - fragile: incorrect expected status code."""
    payload = {
        "name": "John Doe",
        "username": "johndoe",
        "email": "john@example.com"
    }
    response = client.post(f"{BASE_URL}/users", json=payload)
    # FRAGILE: Wrong status code - API returns 201 but test expects 200
    assert response.status_code == 200
    data = response.json()
    assert "id" in data
    assert data["name"] == "John Doe"

def test_update_user_put(client):
    """Test PUT update user - fragile: hardcoded user ID."""
    payload = {
        "name": "Jane Smith",
        "username": "janesmith",
        "email": "jane@example.com"
    }
    # BRITTLE: assumes user ID 1 exists
    response = client.put(f"{BASE_URL}/users/1", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "Jane Smith"

def test_update_user_patch(client):
    """Test PATCH partial update - fragile: field name assumptions."""
    payload = {
        "email": "updated@example.com"
    }
    response = client.patch(f"{BASE_URL}/users/1", json=payload)
    assert response.status_code == 200
    data = response.json()
    # BRITTLE: assumes 'email' field exists in response
    assert data["email"] == "updated@example.com"

def test_delete_user(client):
    """Test DELETE user - fragile: might expect response body."""
    response = client.delete(f"{BASE_URL}/users/1")
    # FRAGILE: Wrong status code - API returns 200 but test expects 204
    assert response.status_code == 204