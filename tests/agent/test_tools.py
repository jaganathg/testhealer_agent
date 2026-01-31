"""Unit tests for agent tools - 2 tests per function."""
import pytest
from pathlib import Path
from src.agent.tools import (
    read_test_file,
    write_test_file,
    run_single_test,
    call_api,
    list_test_files,
    PROJECT_ROOT
)


# ============================================================================
# Tests for read_test_file
# ============================================================================

def test_read_test_file_success():
    """Test reading an existing test file successfully."""
    result = read_test_file("tests/api/test_auth.py")
    assert result["success"] is True
    assert "content" in result
    assert len(result["content"]) > 0
    assert result["error"] is None


def test_read_test_file_invalid_path():
    """Test reading file outside tests/ directory fails."""
    result = read_test_file("src/agent/tools.py")
    assert result["success"] is False
    assert "error" in result
    assert "must be within tests/ directory" in result["error"]


# ============================================================================
# Tests for write_test_file
# ============================================================================

def test_write_test_file_success():
    """Test writing a new file successfully."""
    temp_path = "tests/api/test_temp_tools.py"
    content = "# Temporary test file\nprint('test')\n"
    
    try:
        result = write_test_file(temp_path, content, create_backup=False)
        assert result["success"] is True
        assert result["error"] is None
        
        # Verify file was written
        written_file = Path(PROJECT_ROOT / temp_path)
        assert written_file.exists()
        assert written_file.read_text(encoding="utf-8") == content
    finally:
        # Cleanup
        if Path(PROJECT_ROOT / temp_path).exists():
            Path(PROJECT_ROOT / temp_path).unlink()


def test_write_test_file_invalid_path():
    """Test writing file outside tests/ directory fails."""
    result = write_test_file("src/agent/test.py", "content", create_backup=False)
    assert result["success"] is False
    assert "error" in result
    assert "must be within tests/ directory" in result["error"]


# ============================================================================
# Tests for run_single_test
# ============================================================================

def test_run_single_test_success():
    """Test running an existing test successfully."""
    result = run_single_test("tests/api/test_auth.py::test_get_post")
    assert result["success"] is True
    assert "output" in result
    assert "duration" in result
    assert isinstance(result["duration"], (int, float))
    assert result["duration"] > 0


def test_run_single_test_invalid_path():
    """Test running test with invalid path format fails."""
    result = run_single_test("invalid/path.py")
    assert result["success"] is False
    assert "error" in result
    assert "Must start with 'tests/'" in result["error"]


# ============================================================================
# Tests for call_api
# ============================================================================

def test_call_api_success():
    """Test making a successful API GET request."""
    result = call_api("GET", "/users/1")
    assert result["success"] is True
    assert result["status_code"] == 200
    assert "body" in result
    assert isinstance(result["body"], dict)
    assert "id" in result["body"]


def test_call_api_invalid_method():
    """Test API call with invalid HTTP method fails."""
    result = call_api("INVALID", "/users/1")
    assert result["success"] is False
    assert "error" in result
    assert "Invalid HTTP method" in result["error"]


# ============================================================================
# Tests for list_test_files
# ============================================================================

def test_list_test_files_success():
    """Test listing test files successfully."""
    result = list_test_files()
    assert result["success"] is True
    assert "files" in result
    assert isinstance(result["files"], list)
    assert len(result["files"]) >= 3  # Should have at least 3 test files
    # Verify all are test files
    for file_path in result["files"]:
        assert file_path.startswith("tests/api/")
        assert "test_" in Path(file_path).name


def test_list_test_files_contains_expected():
    """Test that list contains expected test files."""
    result = list_test_files()
    assert result["success"] is True
    files = result["files"]
    # Should contain these test files
    assert "tests/api/test_auth.py" in files
    assert "tests/api/test_resources.py" in files
    assert "tests/api/test_users.py" in files
