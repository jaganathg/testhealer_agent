"""BRITTLE tests for JSONPlaceholder post endpoints."""
import pytest
import httpx

BASE_URL = "https://jsonplaceholder.typicode.com"

def test_get_post(client):
    """Test GET single post - fragile: hardcoded ID and field assertions."""
    response = client.get(f"{BASE_URL}/posts/1")
    assert response.status_code == 200
    data = response.json()
    # BRITTLE: assumes specific field names and values
    assert data["id"] == 1
    assert data["userId"] == 1
    # FRAGILE: Wrong field name - API uses 'title' but test expects 'postTitle'
    assert "postTitle" in data
    assert "body" in data

def test_list_posts(client):
    """Test GET posts list - fragile: hardcoded count expectation."""
    response = client.get(f"{BASE_URL}/posts")
    assert response.status_code == 200
    data = response.json()
    # FRAGILE: Wrong count - API has 100 posts but test expects 99
    assert len(data) == 99

def test_create_post(client):
    """Test POST create post - fragile: status code and response structure."""
    payload = {
        "title": "Test Post",
        "body": "This is a test post",
        "userId": 1
    }
    response = client.post(f"{BASE_URL}/posts", json=payload)
    # BRITTLE: expects 201, but API returns 201 (correct, but brittle)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["title"] == "Test Post"

def test_update_post_put(client):
    """Test PUT update post - fragile: hardcoded post ID."""
    payload = {
        "title": "Updated Post",
        "body": "Updated body",
        "userId": 1
    }
    # BRITTLE: assumes post ID 1 exists
    response = client.put(f"{BASE_URL}/posts/1", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "Updated Post"

def test_update_post_patch(client):
    """Test PATCH partial update - fragile: field name assumptions."""
    payload = {
        "title": "Patched Title"
    }
    response = client.patch(f"{BASE_URL}/posts/1", json=payload)
    assert response.status_code == 200
    data = response.json()
    # BRITTLE: assumes 'title' field exists in response
    assert data["title"] == "Patched Title"

def test_delete_post(client):
    """Test DELETE post - fragile: might expect different status code."""
    response = client.delete(f"{BASE_URL}/posts/1")
    # BRITTLE: expects 200, but API returns 200 (correct, but brittle)
    assert response.status_code == 200

def test_get_post_not_found(client):
    """Test GET non-existent post."""
    response = client.get(f"{BASE_URL}/posts/999")
    # BRITTLE: might expect 404 but API returns 200 with empty object
    assert response.status_code == 404