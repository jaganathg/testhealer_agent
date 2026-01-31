"""Agent tools for reading files, writing fixes, executing tests, and calling APIs."""
import json
import os
import subprocess
import shutil
import time
import logging
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Dict, Any
import httpx
from pydantic import BaseModel, Field
from langchain_core.tools import StructuredTool

logger = logging.getLogger(__name__)

# Constants
PROJECT_ROOT = Path(__file__).parent.parent.parent
TESTS_DIR = PROJECT_ROOT / "tests" / "api"
BACKUP_DIR = PROJECT_ROOT / "failures" / ".backups"
API_BASE_URL = "https://jsonplaceholder.typicode.com"

# Create backup directory if it doesn't exist
BACKUP_DIR.mkdir(parents=True, exist_ok=True)


# Helper Functions

def _validate_test_file_path(file_path: str) -> tuple[bool, Optional[str]]:
    """
    Validate file path is within project and in tests/ directory.
    
    Returns:
        (is_valid, error_message)
    """
    try:
        # Convert to absolute path
        abs_path = Path(file_path).resolve()
        
        # Check if within PROJECT_ROOT
        try:
            abs_path.relative_to(PROJECT_ROOT)
        except ValueError:
            return False, f"Path {file_path} is outside project root"
        
        # Check if path is in tests/ directory (allow tests/ or tests/api/)
        tests_root = PROJECT_ROOT / "tests"
        try:
            abs_path.relative_to(tests_root)
        except ValueError:
            return False, f"Path {file_path} must be within tests/ directory"
        
        return True, None
    except Exception as e:
        return False, f"Invalid path: {str(e)}"


def _create_backup(file_path: str) -> Optional[str]:
    """
    Create backup of file before modification.
    
    Returns:
        backup_path or None if failed
    """
    try:
        abs_path = Path(file_path).resolve()
        
        if not abs_path.exists():
            logger.warning(f"Backup skipped: File does not exist - {file_path}")
            return None
        
        # Generate backup filename: {original_name}.backup.{timestamp}
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_filename = f"{abs_path.stem}.backup.{timestamp}{abs_path.suffix}"
        backup_path = BACKUP_DIR / backup_filename
        
        # Copy file to backup location
        shutil.copy2(abs_path, backup_path)
        logger.info(f"Backup created: {backup_path}")
        
        return str(backup_path)
    except Exception as e:
        logger.error(f"Backup failed for {file_path}: {str(e)}", exc_info=True)
        return None


# Pydantic Input Models

class ReadTestFileInput(BaseModel):
    """Input model for read_test_file tool."""
    file_path: str = Field(description="Path to test file (relative or absolute)")


class WriteTestFileInput(BaseModel):
    """Input model for write_test_file tool."""
    file_path: str = Field(description="Path to test file to write")
    content: str = Field(description="Complete file content to write")
    create_backup: bool = Field(default=True, description="Create backup before writing")


class RunSingleTestInput(BaseModel):
    """Input model for run_single_test tool."""
    test_path: str = Field(
        description="Test path: 'tests/api/test_file.py::test_function' or 'tests/api/test_file.py'"
    )


class CallAPIInput(BaseModel):
    """Input model for call_api tool."""
    method: str = Field(description="HTTP method: GET, POST, PUT, DELETE, PATCH")
    url: str = Field(description="Full URL or relative path (e.g., '/users/1')")
    payload: Optional[Dict[str, Any]] = Field(
        default=None, description="Request body for POST/PUT/PATCH"
    )


# Tool Functions

def read_test_file(file_path: str) -> Dict[str, Any]:
    """
    Read content of a test file.
    
    Args:
        file_path: Path to test file (relative or absolute)
    
    Returns:
        {
            "success": bool,
            "content": str (if success),
            "error": str (if failed)
        }
    """
    try:
        # Validate path
        is_valid, error_msg = _validate_test_file_path(file_path)
        if not is_valid:
            return {"success": False, "content": None, "error": error_msg}
        
        # Convert to absolute path
        abs_path = Path(file_path).resolve()
        
        # Check if file exists
        if not abs_path.exists():
            return {"success": False, "content": None, "error": f"File not found: {file_path}"}
        
        # Read file content
        content = abs_path.read_text(encoding="utf-8")
        
        return {"success": True, "content": content, "error": None}
    
    except Exception as e:
        return {"success": False, "content": None, "error": f"Error reading file: {str(e)}"}


def write_test_file(file_path: str, content: str, create_backup: bool = True) -> Dict[str, Any]:
    """
    Write or update a test file. Automatically creates backup if create_backup=True.
    
    Args:
        file_path: Path to test file
        content: New file content to write
        create_backup: Whether to create backup before writing (default: True)
    
    Returns:
        {
            "success": bool,
            "backup_path": str (if backup created),
            "error": str (if failed)
        }
    """
    try:
        # Validate path
        is_valid, error_msg = _validate_test_file_path(file_path)
        if not is_valid:
            return {"success": False, "backup_path": None, "error": error_msg}
        
        # Convert to absolute path
        abs_path = Path(file_path).resolve()
        
        # Create backup if requested and file exists
        backup_path = None
        if create_backup and abs_path.exists():
            backup_path = _create_backup(file_path)
            if backup_path is None:
                return {
                    "success": False,
                    "backup_path": None,
                    "error": "Failed to create backup"
                }
        
        # Ensure parent directory exists
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write content to file
        abs_path.write_text(content, encoding="utf-8")
        
        return {
            "success": True,
            "backup_path": backup_path,
            "error": None
        }
    
    except Exception as e:
        return {"success": False, "backup_path": None, "error": f"Error writing file: {str(e)}"}


def run_single_test(test_path: str) -> Dict[str, Any]:
    """
    Execute a single test using pytest.
    
    Args:
        test_path: Test path in format "tests/api/test_file.py::test_function_name"
                   or just "tests/api/test_file.py" to run all tests in file
    
    Returns:
        {
            "success": bool (execution succeeded),
            "passed": bool (test passed),
            "output": str (pytest output),
            "duration": float (seconds),
            "error": str (if execution failed)
        }
    """
    try:
        # Validate test_path format
        if not test_path.startswith("tests/"):
            return {
                "success": False,
                "passed": False,
                "output": "",
                "duration": 0.0,
                "error": f"Invalid test path format: {test_path}. Must start with 'tests/'"
            }
        
        # Build pytest command
        cmd = ["pytest", test_path, "-v", "--tb=short"]
        
        # Record start time
        start_time = time.time()
        
        # Run pytest
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=30,  # 30 second timeout
            cwd=str(PROJECT_ROOT)
        )
        
        # Calculate duration
        duration = time.time() - start_time
        
        # Combine stdout and stderr
        output = result.stdout + result.stderr
        
        # Determine if test passed
        # pytest returns 0 on success, non-zero on failure
        passed = result.returncode == 0
        
        # Check output for pass indicators
        if "PASSED" in output or "passed" in output.lower():
            passed = True
        elif "FAILED" in output or "failed" in output.lower():
            passed = False
        
        return {
            "success": True,
            "passed": passed,
            "output": output,
            "duration": round(duration, 2),
            "error": None
        }
    
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "passed": False,
            "output": "",
            "duration": 30.0,
            "error": "Test execution timed out after 30 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "passed": False,
            "output": "",
            "duration": 0.0,
            "error": f"Error running test: {str(e)}"
        }


def call_api(method: str, url: str, payload: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """
    Make HTTP request to target API.
    
    Args:
        method: HTTP method (GET, POST, PUT, DELETE, PATCH)
        url: Full URL or relative path (will prepend API_BASE_URL if relative)
        payload: Request body for POST/PUT/PATCH (optional)
    
    Returns:
        {
            "success": bool,
            "status_code": int,
            "body": Any (parsed JSON or text),
            "headers": Dict[str, str],
            "error": str (if failed)
        }
    """
    try:
        # Validate method
        method = method.upper()
        allowed_methods = ["GET", "POST", "PUT", "DELETE", "PATCH"]
        if method not in allowed_methods:
            return {
                "success": False,
                "status_code": 0,
                "body": None,
                "headers": {},
                "error": f"Invalid HTTP method: {method}. Allowed: {allowed_methods}"
            }
        
        # Handle relative URLs
        if not url.startswith("http://") and not url.startswith("https://"):
            # Remove leading slash if present
            url = url.lstrip("/")
            full_url = f"{API_BASE_URL}/{url}"
        else:
            full_url = url
        
        # Prepare request
        if method == "GET":
            response = httpx.get(full_url, timeout=10.0)
        elif method == "POST":
            response = httpx.post(full_url, json=payload, timeout=10.0)
        elif method == "PUT":
            response = httpx.put(full_url, json=payload, timeout=10.0)
        elif method == "DELETE":
            response = httpx.delete(full_url, timeout=10.0)
        elif method == "PATCH":
            response = httpx.patch(full_url, json=payload, timeout=10.0)
        
        # Parse response body
        try:
            body = response.json()
        except Exception:
            body = response.text
        
        # Convert headers to dict
        headers = dict(response.headers)
        
        return {
            "success": True,
            "status_code": response.status_code,
            "body": body,
            "headers": headers,
            "error": None
        }
    
    except httpx.TimeoutException:
        return {
            "success": False,
            "status_code": 0,
            "body": None,
            "headers": {},
            "error": "Request timed out after 10 seconds"
        }
    except Exception as e:
        return {
            "success": False,
            "status_code": 0,
            "body": None,
            "headers": {},
            "error": f"Error making API request: {str(e)}"
        }


def list_test_files() -> Dict[str, Any]:
    """
    List all test files in tests/api/ directory.
    
    Returns:
        {
            "success": bool,
            "files": List[str] (list of file paths),
            "error": str (if failed)
        }
    """
    try:
        # Check if TESTS_DIR exists
        if not TESTS_DIR.exists():
            return {
                "success": False,
                "files": [],
                "error": f"Tests directory not found: {TESTS_DIR}"
            }
        
        # Find all test_*.py files
        test_files = list(TESTS_DIR.glob("test_*.py"))
        
        # Convert to relative paths
        files = [str(f.relative_to(PROJECT_ROOT)) for f in test_files]
        files.sort()
        
        return {
            "success": True,
            "files": files,
            "error": None
        }
    
    except Exception as e:
        return {
            "success": False,
            "files": [],
            "error": f"Error listing test files: {str(e)}"
        }


# LangChain Tool Wrappers

read_test_file_tool = StructuredTool.from_function(
    func=read_test_file,
    name="read_test_file",
    description="Read the content of a test file. Use this to examine existing test code before making fixes.",
    args_schema=ReadTestFileInput
)

write_test_file_tool = StructuredTool.from_function(
    func=write_test_file,
    name="write_test_file",
    description="Write or update a test file. Automatically creates a backup before modification for safety.",
    args_schema=WriteTestFileInput
)

run_single_test_tool = StructuredTool.from_function(
    func=run_single_test,
    name="run_single_test",
    description="Execute a single test or test file using pytest. Use this to validate fixes after modifying test code.",
    args_schema=RunSingleTestInput
)

call_api_tool = StructuredTool.from_function(
    func=call_api,
    name="call_api",
    description="Make HTTP request to the target API. Use this to verify API responses and understand actual behavior.",
    args_schema=CallAPIInput
)

list_test_files_tool = StructuredTool.from_function(
    func=list_test_files,
    name="list_test_files",
    description="List all test files in the tests/api/ directory. Use this to discover available tests.",
    args_schema=None
)


# Exports

# List of all tools for agent binding
ALL_TOOLS = [
    read_test_file_tool,
    write_test_file_tool,
    run_single_test_tool,
    call_api_tool,
    list_test_files_tool,
]

# Individual exports
__all__ = [
    "read_test_file",
    "write_test_file",
    "run_single_test",
    "call_api",
    "list_test_files",
    "ALL_TOOLS",
    "read_test_file_tool",
    "write_test_file_tool",
    "run_single_test_tool",
    "call_api_tool",
    "list_test_files_tool",
]