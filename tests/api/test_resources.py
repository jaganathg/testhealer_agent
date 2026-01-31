"""BRITTLE tests for JSONPlaceholder comment endpoints."""
import pytest
import httpx

BASE_URL = "https://jsonplaceholder.typicode.com"

def test_list_comments(client):
    """Test GET comments list - fragile: hardcoded count expectation."""
    response = client.get(f"{BASE_URL}/comments")
    assert response.status_code == 200
    data = response.json()
    # FRAGILE: Wrong count - API has 500 comments but test expects 501
    assert len(data) == 501

def test_get_single_comment(client):
    """Test GET single comment - fragile: hardcoded ID and field names."""
    response = client.get(f"{BASE_URL}/comments/1")
    assert response.status_code == 200
    data = response.json()
    # BRITTLE: assumes specific field names and values
    assert data["id"] == 1
    assert data["postId"] == 1
    assert "name" in data
    assert "email" in data
    # FRAGILE: Wrong field name - API uses 'body' but test expects 'commentBody'
    assert "commentBody" in data

def test_get_comment_not_found(client):
    """Test GET non-existent comment."""
    response = client.get(f"{BASE_URL}/comments/999")
    # FRAGILE: Wrong status code - API returns 404 but test expects 200
    assert response.status_code == 200

def test_get_comments_by_post(client):
    """Test GET comments filtered by post ID - fragile: hardcoded post ID."""
    response = client.get(f"{BASE_URL}/posts/1/comments")
    assert response.status_code == 200
    data = response.json()
    # BRITTLE: assumes post 1 has exactly 5 comments
    assert len(data) == 5
    # BRITTLE: assumes all comments belong to post 1
    assert all(comment["postId"] == 1 for comment in data)