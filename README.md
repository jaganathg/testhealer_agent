# Self-Healing API Test Agent

An LLM-powered agent that automatically detects API test failures, diagnoses root causes, fixes broken test scripts, and generates missing critical test cases.

## Project Overview

This project builds an intelligent test automation system that uses Claude (via Anthropic API) to automatically heal failing API tests. When tests break due to API changes, the agent analyzes the failure, understands the root cause, and generates fixes. It can also identify coverage gaps and generate critical missing test cases.

The target API for demonstration is **ReqRes.in**, a free REST API that provides predictable endpoints for users, resources, and authentication.

## Current Implementation

### Environment Setup

The project is built with Python 3.12+ and uses `uv` as the package manager for fast dependency resolution. A virtual environment (`.venv`) has been created and configured to isolate project dependencies.

All required packages have been installed:
- **LangChain** and **LangChain Anthropic** for agent orchestration
- **pytest** for test execution
- **httpx** for HTTP requests
- **pydantic** for data validation
- **python-dotenv** for environment management
- **rich** for enhanced terminal output

### Project Structure

The codebase is organized into modular components:

```
testhealer_agent/
├── src/
│   ├── agent/          # Core healer agent (to be implemented)
│   ├── analyzer/       # Failure analysis module (to be implemented)
│   └── generator/      # Test generation module (to be implemented)
├── tests/
│   └── api/           # API test suite (to be implemented)
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

## How It Works

The agent follows a reactive healing approach:

1. **Test Execution**: Runs the API test suite against ReqRes.in
2. **Failure Detection**: Captures any test failures with full context
3. **Root Cause Analysis**: Uses Claude to diagnose why the test failed
4. **Fix Generation**: Automatically generates corrected test code
5. **Validation**: Applies the fix, re-runs the test, and verifies success
6. **Test Generation**: Identifies missing critical test cases and generates them

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

## Next Steps

The foundation is in place. The project will continue with building the test suite, implementing failure analysis, creating agent tools, and developing the core healing logic.
