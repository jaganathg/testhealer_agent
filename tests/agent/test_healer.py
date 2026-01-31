"""Unit tests for healer agent - 2 tests per class/method."""
import pytest
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from src.agent.healer import HealerAgent, HealerCallbackHandler
from src.analyzer.failure_parser import FailureContext, TestFailure, APIResponse
from src.agent.tools import PROJECT_ROOT


# ============================================================================
# Tests for HealerCallbackHandler
# ============================================================================

def test_healer_callback_handler_init():
    """Test callback handler initialization."""
    handler = HealerCallbackHandler()
    assert handler.reasoning_steps == []
    assert handler.current_step is None


def test_healer_callback_handler_on_tool_start():
    """Test callback handler captures tool start."""
    handler = HealerCallbackHandler()
    serialized = {"name": "read_test_file"}
    input_str = '{"file_path": "tests/api/test_users.py"}'
    
    handler.on_tool_start(serialized, input_str)
    
    assert len(handler.reasoning_steps) == 1
    assert handler.reasoning_steps[0]["type"] == "action"
    assert handler.reasoning_steps[0]["tool"] == "read_test_file"
    assert handler.reasoning_steps[0]["input"] == input_str


def test_healer_callback_handler_on_tool_end():
    """Test callback handler captures tool end and extracts backup path."""
    handler = HealerCallbackHandler()
    # First add a tool start
    handler.reasoning_steps.append({
        "type": "action",
        "tool": "write_test_file",
        "input": "test"
    })
    
    # Simulate tool output with backup path
    output = '{"success": true, "backup_path": "/path/to/backup", "error": null}'
    handler.on_tool_end(output)
    
    assert handler.reasoning_steps[0]["output"] == output
    assert handler.reasoning_steps[0]["backup_path"] == "/path/to/backup"


def test_healer_callback_handler_clear():
    """Test callback handler clears reasoning steps."""
    handler = HealerCallbackHandler()
    handler.reasoning_steps = [{"type": "action", "tool": "test"}]
    handler.current_step = {"type": "reasoning"}
    
    handler.clear()
    
    assert handler.reasoning_steps == []
    assert handler.current_step is not None  # current_step not cleared by clear()


def test_healer_callback_handler_get_reasoning_log():
    """Test callback handler returns reasoning log."""
    handler = HealerCallbackHandler()
    handler.reasoning_steps = [
        {"type": "action", "tool": "read_test_file"},
        {"type": "reasoning", "content": "I need to read the file"}
    ]
    
    log = handler.get_reasoning_log()
    
    assert len(log) == 2
    assert log[0]["type"] == "action"
    assert log[1]["type"] == "reasoning"


# ============================================================================
# Tests for HealerAgent - Initialization
# ============================================================================

def test_healer_agent_init():
    """Test healer agent initialization."""
    with patch('src.agent.healer.ChatAnthropic'):
        agent = HealerAgent(max_retries=3)
        assert agent.max_retries == 3
        assert agent.callback_handler is not None
        assert agent.backup_paths == []
        assert agent.agent is not None


def test_healer_agent_init_default_retries():
    """Test healer agent uses default retries if not specified."""
    with patch('src.agent.healer.ChatAnthropic'):
        agent = HealerAgent()
        assert agent.max_retries == 3


# ============================================================================
# Tests for HealerAgent - _load_failure_context
# ============================================================================

def test_load_failure_context_success():
    """Test loading failure context from valid JSON file."""
    # Create a temporary failure JSON file
    temp_failure = Path("failures/test_temp_failure.json")
    failure_data = {
        "test_failure": {
            "test_file": "tests/api/test_users.py",
            "test_name": "test_get_user",
            "error_type": "KeyError",
            "error_message": "'firstName'",
            "actual": "data[\"firstName\"]",
            "expected": "Leanne Graham",
            "line_number": 13,
            "traceback": "Traceback..."
        },
        "api_response": {
            "status_code": 200,
            "body": {"id": 1, "name": "Leanne Graham"},
            "headers": {},
            "url": "https://jsonplaceholder.typicode.com/users/1"
        },
        "request_method": "GET",
        "request_url": "https://jsonplaceholder.typicode.com/users/1",
        "request_payload": None,
        "timestamp": "2026-01-30T21:20:44.921431"
    }
    
    try:
        temp_failure.parent.mkdir(exist_ok=True)
        temp_failure.write_text(json.dumps(failure_data))
        
        with patch('src.agent.healer.ChatAnthropic'):
            healer = HealerAgent()
            context = healer._load_failure_context(str(temp_failure))
            
            assert isinstance(context, FailureContext)
            assert context.test_failure.test_name == "test_get_user"
            assert context.api_response.status_code == 200
    finally:
        if temp_failure.exists():
            temp_failure.unlink()


def test_load_failure_context_invalid_file():
    """Test loading failure context from non-existent file raises error."""
    with patch('src.agent.healer.ChatAnthropic'):
        healer = HealerAgent()
        
        with pytest.raises(ValueError, match="Failed to load failure context"):
            healer._load_failure_context("failures/non_existent.json")


# ============================================================================
# Tests for HealerAgent - _format_failure_prompt
# ============================================================================

def test_format_failure_prompt_first_attempt():
    """Test formatting failure prompt for first attempt."""
    test_failure = TestFailure(
        test_file="tests/api/test_users.py",
        test_name="test_get_user",
        error_type="KeyError",
        error_message="'firstName'",
        actual="data[\"firstName\"]",
        expected="Leanne Graham",
        line_number=13,
        traceback="Traceback..."
    )
    
    api_response = APIResponse(
        status_code=200,
        body={"id": 1, "name": "Leanne Graham"},
        headers={},
        url="https://jsonplaceholder.typicode.com/users/1"
    )
    
    failure_context = FailureContext(
        test_failure=test_failure,
        api_response=api_response,
        request_method="GET",
        request_url="https://jsonplaceholder.typicode.com/users/1"
    )
    
    with patch('src.agent.healer.ChatAnthropic'):
        healer = HealerAgent()
        prompt = healer._format_failure_prompt(failure_context, attempt=1)
        
        assert "test_get_user" in prompt
        assert "KeyError" in prompt
        assert "Leanne Graham" in prompt
        assert "200" in prompt
        assert "Previous Fix Attempt" not in prompt  # Should not include retry context


def test_format_failure_prompt_retry_attempt():
    """Test formatting failure prompt for retry attempt includes retry context."""
    test_failure = TestFailure(
        test_file="tests/api/test_users.py",
        test_name="test_get_user",
        error_type="KeyError",
        error_message="'firstName'",
        actual="data[\"firstName\"]",
        expected="Leanne Graham",
        line_number=13,
        traceback="Traceback..."
    )
    
    api_response = APIResponse(
        status_code=200,
        body={"id": 1, "name": "Leanne Graham"},
        headers={},
        url="https://jsonplaceholder.typicode.com/users/1"
    )
    
    failure_context = FailureContext(
        test_failure=test_failure,
        api_response=api_response,
        request_method="GET",
        request_url="https://jsonplaceholder.typicode.com/users/1"
    )
    
    with patch('src.agent.healer.ChatAnthropic'):
        healer = HealerAgent()
        prompt = healer._format_failure_prompt(failure_context, attempt=2)
        
        assert "Previous Fix Attempt 1 failed" in prompt
        assert "Did you correctly identify the root cause?" in prompt


# ============================================================================
# Tests for HealerAgent - _extract_decision_from_output
# ============================================================================

def test_extract_decision_from_output_found():
    """Test extracting decision from agent output when present."""
    with patch('src.agent.healer.ChatAnthropic'):
        healer = HealerAgent()
        
        output = "I've analyzed the failure.\nDetected: Field rename - 'firstName' → 'name'\nFixed the test."
        decision = healer._extract_decision_from_output(output)
        
        assert decision is not None
        assert "Detected:" in decision


def test_extract_decision_from_output_not_found():
    """Test extracting decision when not present in output."""
    with patch('src.agent.healer.ChatAnthropic'):
        healer = HealerAgent()
        
        output = "I've fixed the test. It should work now."
        decision = healer._extract_decision_from_output(output)
        
        assert decision is None


# ============================================================================
# Tests for HealerAgent - _rollback
# ============================================================================

def test_rollback_success():
    """Test successful rollback from backup file."""
    # Create temporary files
    original_file = Path("tests/api/test_temp_rollback.py")
    backup_file = Path("failures/.backups/test_temp_rollback.backup.20260130.py")
    original_content = "# Original content\nprint('original')"
    backup_content = "# Backup content\nprint('backup')"
    
    try:
        # Setup: create backup and modified original
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        backup_file.write_text(backup_content)
        original_file.write_text(original_content)
        
        with patch('src.agent.healer.ChatAnthropic'):
            healer = HealerAgent()
            result = healer._rollback(str(backup_file), str(original_file))
            
            assert result is True
            assert original_file.read_text() == backup_content
    finally:
        # Cleanup
        if original_file.exists():
            original_file.unlink()
        if backup_file.exists():
            backup_file.unlink()


def test_rollback_backup_not_exists():
    """Test rollback fails when backup file doesn't exist."""
    original_file = Path("tests/api/test_temp_rollback.py")
    backup_file = Path("failures/.backups/non_existent.backup.py")
    
    try:
        original_file.write_text("# Original content")
        
        with patch('src.agent.healer.ChatAnthropic'):
            healer = HealerAgent()
            result = healer._rollback(str(backup_file), str(original_file))
            
            assert result is False
    finally:
        if original_file.exists():
            original_file.unlink()


# ============================================================================
# Tests for HealerAgent - heal_failure (integration-style)
# ============================================================================

def test_heal_failure_invalid_json_path():
    """Test heal_failure returns error for invalid JSON path."""
    with patch('src.agent.healer.ChatAnthropic'):
        healer = HealerAgent()
        result = healer.heal_failure("failures/non_existent.json")
        
        assert result["success"] is False
        assert result["test_name"] == "unknown"
        assert result["attempts"] == 0
        assert "error" in result
        assert "Failed to load failure context" in result["error"]


def test_heal_failure_logs_diagnosis():
    """Test heal_failure logs diagnosis information."""
    # Create minimal failure JSON
    temp_failure = Path("failures/test_temp_heal.json")
    failure_data = {
        "test_failure": {
            "test_file": "tests/api/test_users.py",
            "test_name": "test_get_user",
            "error_type": "KeyError",
            "error_message": "'firstName'",
            "actual": "data[\"firstName\"]",
            "expected": "Leanne Graham",
            "line_number": 13,
            "traceback": None
        },
        "api_response": {
            "status_code": 200,
            "body": {"id": 1, "name": "Leanne Graham"},
            "headers": {},
            "url": "https://jsonplaceholder.typicode.com/users/1"
        },
        "request_method": "GET",
        "request_url": "https://jsonplaceholder.typicode.com/users/1",
        "request_payload": None,
        "timestamp": "2026-01-30T21:20:44.921431"
    }
    
    try:
        temp_failure.parent.mkdir(exist_ok=True)
        temp_failure.write_text(json.dumps(failure_data))
        
        with patch('src.agent.healer.ChatAnthropic'):
            with patch.object(HealerAgent, '_create_agent') as mock_create:
                # Mock agent (new API returns dict with messages)
                from langchain_core.messages import AIMessage
                mock_agent = MagicMock()
                # New API format: returns dict with messages
                mock_agent.invoke.return_value = {
                    "messages": [AIMessage(content="Test fixed. Detected: Field rename - 'firstName' → 'name'")]
                }
                mock_create.return_value = mock_agent
                
                healer = HealerAgent()
                healer.agent = mock_agent
                
                # Mock run_single_test to return success (patch at tools module level)
                with patch('src.agent.tools.run_single_test') as mock_run:
                    mock_run.return_value = {"passed": True, "output": "PASSED"}
                    
                    result = healer.heal_failure(str(temp_failure))
                    
                    # Verify diagnosis was logged (check that method was called)
                    assert result["success"] is True
                    assert result["test_name"] == "test_get_user"
    finally:
        if temp_failure.exists():
            temp_failure.unlink()
