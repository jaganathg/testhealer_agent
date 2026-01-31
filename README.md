# Self-Healing API Test Agent

An LLM-powered agent that automatically detects API test failures, diagnoses root causes, fixes broken test scripts, and generates missing critical test cases.

## Project Overview

This project builds an intelligent test automation system that uses Claude (via Anthropic API) to automatically heal failing API tests. When tests break due to API changes, the agent analyzes the failure, understands the root cause, and generates fixes. It can also identify coverage gaps and generate critical missing test cases.

The target API for demonstration is **JSONPlaceholder**, a free REST API that provides predictable endpoints for users, posts, comments, and other resources.

## Environment Setup

The project is built with Python 3.12+ and uses `uv` as the package manager for fast dependency resolution. A virtual environment (`.venv`) has been created and configured to isolate project dependencies.

All required packages have been installed:
- **LangChain** and **LangChain Anthropic** for agent orchestration
- **pytest** for test execution
- **httpx** for HTTP requests
- **pydantic** for data validation
- **python-dotenv** for environment management
- **rich** for enhanced terminal output

## Project Structure

### Folder

The codebase is organized into modular components:

```
testhealer_agent/
├── src/
│   ├── agent/          # Core healer agent (to be implemented)
│   ├── analyzer/       # ✅ Failure analysis module (IMPLEMENTED)
│   │   └── failure_parser.py  # Pydantic data models
│   └── generator/      # Test generation module (to be implemented)
├── tests/
│   ├── conftest.py     # ✅ Pytest hooks and HTTP tracking (IMPLEMENTED)
│   └── api/           # API test suite
│       ├── test_users.py      # User CRUD endpoints
│       ├── test_auth.py        # Post endpoints
│       └── test_resources.py   # Comment endpoints
├── failures/           # ✅ Auto-generated failure JSON files (CREATED)
├── config/
│   └── settings.py    # Configuration management
├── doc/               # Project documentation
└── pyproject.toml     # Project dependencies
```

### Configuration

The configuration system is set up to securely manage API keys. Environment variables are loaded from a `.env` file using `python-dotenv`. The `config/settings.py` module validates that the `ANTHROPIC_API_KEY` is present before the application runs, ensuring proper API access.

To use the project, create a `.env` file in the root directory:

```env
ANTHROPIC_API_KEY=your_api_key_here
```

## Getting Started

### Prerequisites

- Python 3.12 or higher
- uv package manager ([installation guide](https://github.com/astral-sh/uv))
- Anthropic API key

### Setup

1. **Activate the virtual environment:**
   ```bash
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   ```

2. **Verify configuration:**
   ```bash
   python -c "from config.settings import ANTHROPIC_API_KEY; print('Configuration loaded successfully')"
   ```

3. **Install/update dependencies (if needed):**
   ```bash
   uv sync
   ```

4. **Run the test suite:**
   ```bash
   pytest tests/api/ -v
   ```
   Expected output: 10 failures and 8 passes (intentional fragility for healing demonstration)

## Test Suite

A comprehensive API test suite has been created to serve as healing targets for the agent. The suite consists of **18 tests** organized across three test files, covering user management, post operations, and comment endpoints.

**Test Coverage:**
- **User endpoints** (`test_users.py`): Seven tests covering GET, POST, PUT, PATCH, and DELETE operations for user resources
- **Post endpoints** (`test_auth.py`): Seven tests for post CRUD operations and list retrieval
- **Comment endpoints** (`test_resources.py`): Four tests for comment listing, single retrieval, and filtered queries

The test suite has been intentionally designed with fragility points to demonstrate the healing capabilities. Currently, **8 tests pass** successfully, providing a baseline of working functionality, while **10 tests fail** due to intentional mismatches that the agent will need to diagnose and fix.

**Fragility Markers:**
- Tests marked with `# FRAGILE:` indicate broken assertions that require healing (10 instances)
- Tests marked with `# BRITTLE:` indicate working tests with assumptions that could break under API changes (13 instances)

**Failure Types:**
The intentional failures include three categories of break points:
- **Field name mismatches**: Tests expecting different field names than the API provides (3 failures)
- **Status code mismatches**: Tests expecting different HTTP status codes than the API returns (4 failures)
- **Count expectation mismatches**: Tests expecting different collection sizes than the API provides (3 failures)

These break points are documented in the test code and will serve as realistic scenarios for the healing agent to diagnose and repair.

## Failure Analyzer Module

The failure analyzer module automatically captures test failures with complete context, including HTTP request/response data, test metadata, and assertion details. This structured data enables the healing agent to diagnose and fix failures accurately.

**Components:**
- **Pydantic Data Models** (`src/analyzer/failure_parser.py`): Structured data models for failure context
- **Pytest Hooks** (`tests/conftest.py`): Automatic failure interception and capture
- **HTTP Request Tracking**: Captures all HTTP requests and responses made during tests

### Data Models

The failure analyzer uses three Pydantic models to structure failure data:

1. **`APIResponse`**: Captures HTTP response data
   - Status code, response body (JSON or text), headers, and URL
   - Enables the agent to see what the API actually returned

2. **`TestFailure`**: Captures test failure metadata
   - Test file path, function name, error type, error message
   - Actual vs expected values (extracted from assertions)
   - Line number and full traceback

3. **`FailureContext`**: Complete failure context combining test failure + HTTP data
   - Includes request method, URL, payload
   - Timestamp for tracking
   - Serialization methods for JSON export

### Automatic Failure Capture

When a test fails, the system automatically:

1. **Intercepts the failure** using pytest's `pytest_runtest_makereport` hook
2. **Extracts test metadata** (file, function name, line number, error details)
3. **Retrieves HTTP context** (request/response data captured during test execution)
4. **Parses assertion errors** to extract actual vs expected values using regex patterns
5. **Structures the data** into `FailureContext` objects
6. **Exports to JSON** files in the `failures/` directory

### HTTP Request Tracking

The `TrackingClient` wrapper intercepts all HTTP requests made during tests:

- **Tracks requests**: Method, URL, and payload (for POST/PUT/PATCH)
- **Captures responses**: Status code, body, headers, and final URL
- **Stores immediately**: Data is persisted before test completion to ensure availability
- **Handles failures**: Even if HTTP requests fail, request data is still captured

### Failure JSON Structure

Each failure is saved as a JSON file with the following structure:

```json
{
  "test_failure": {
    "test_file": "/path/to/test_file.py",
    "test_name": "test_get_user",
    "error_type": "KeyError",
    "error_message": "'firstName'",
    "actual": "data[\"firstName\"]",
    "expected": "Leanne Graham",
    "line_number": 13,
    "traceback": "..."
  },
  "api_response": {
    "status_code": 200,
    "body": {"name": "Leanne Graham", "id": 1, ...},
    "headers": {...},
    "url": "https://jsonplaceholder.typicode.com/users/1"
  },
  "request_method": "GET",
  "request_url": "https://jsonplaceholder.typicode.com/users/1",
  "request_payload": null,
  "timestamp": "2026-01-30T21:20:44.921431"
}
```

### Usage

**Running tests with failure capture:**

```bash
pytest tests/api/ -v
```

When tests fail, JSON files are automatically created in the `failures/` directory:
- One JSON file per failed test
- Filename format: `{test_name}_{sanitized_nodeid}.json`
- Contains complete context for agent analysis

**Example output:**
```
[FAILURE CAPTURED] test_get_user -> failures/test_get_user_tests_api_test_users.py_test_get_user.json
```

### Key Features

- **Automatic capture**: No code changes needed in test files
- **Complete context**: HTTP request/response data + test failure details
- **Structured data**: Pydantic models ensure data validation and type safety
- **Error extraction**: Intelligent parsing of assertion errors to extract actual/expected values
- **Persistent storage**: JSON files persist for agent analysis and debugging

### How It Works

The agent follows a reactive healing approach:

1. **Test Execution**: Runs the API test suite against JSONPlaceholder
2. **Failure Detection**: Captures any test failures with full context
3. **Root Cause Analysis**: Uses Claude to diagnose why the test failed
4. **Fix Generation**: Automatically generates corrected test code
5. **Validation**: Applies the fix, re-runs the test, and verifies success
6. **Test Generation**: Identifies missing critical test cases and generates them

## Next Steps

The failure analyzer module is fully implemented and capturing test failures with complete HTTP context. Failure JSON files are automatically generated in the `failures/` directory for each test failure.

**Upcoming Development:**
- **Agent Tools Development**: Create tools for file operations, test execution, and API calls
- **Healer Agent Core**: Build the LangChain agent with Claude integration for diagnosis and fix generation
- **Test Generator Module**: Add capability to generate missing critical test cases
- **Integration & Orchestration**: Wire all components into a single CLI workflow
