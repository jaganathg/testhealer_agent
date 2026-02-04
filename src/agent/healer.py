"""Healer Agent - Core module for diagnosing and fixing test failures."""
import json
import logging
from pathlib import Path
from typing import Dict, Any, Optional, List
from langchain_anthropic import ChatAnthropic
from langchain.agents import create_agent
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from config.settings import ANTHROPIC_API_KEY
from src.agent.tools import ALL_TOOLS
from src.analyzer.failure_parser import FailureContext

logger = logging.getLogger(__name__)


class HealerCallbackHandler(BaseCallbackHandler):
    """Custom callback handler to capture agent reasoning for demo logging."""
    
    def __init__(self):
        super().__init__()
        self.reasoning_steps: List[Dict[str, Any]] = []
        self.current_step: Optional[Dict[str, Any]] = None
    
    def on_llm_start(self, serialized: Dict[str, Any], prompts: List[str], **kwargs) -> None:
        """Called when LLM starts generating."""
        self.current_step = {
            "type": "reasoning",
            "content": prompts[0] if prompts else ""
        }
    
    def on_llm_end(self, response: LLMResult, **kwargs) -> None:
        """Called when LLM finishes generating."""
        if self.current_step:
            # Extract the generated text from LLMResult
            if response.generations and len(response.generations) > 0:
                if response.generations[0] and len(response.generations[0]) > 0:
                    generated_text = response.generations[0][0].text
                    self.current_step["content"] = generated_text
                    self.reasoning_steps.append(self.current_step.copy())
            self.current_step = None
    
    def on_tool_start(self, serialized: Dict[str, Any], input_str: str, **kwargs) -> None:
        """Called when agent starts using a tool."""
        tool_name = serialized.get("name", "unknown_tool")
        self.reasoning_steps.append({
            "type": "action",
            "tool": tool_name,
            "input": input_str
        })
    
    def on_tool_end(self, output: str, **kwargs) -> None:
        """Called when tool finishes execution."""
        if self.reasoning_steps and self.reasoning_steps[-1].get("type") == "action":
            self.reasoning_steps[-1]["output"] = output
            
            # Extract backup path from write_test_file output
            if self.reasoning_steps[-1].get("tool") == "write_test_file":
                try:
                    import json
                    # Output might be a string representation of dict or actual dict
                    if isinstance(output, str):
                        # Try to parse as JSON
                        try:
                            output_dict = json.loads(output)
                        except:
                            # If not JSON, try to extract from string representation
                            # LangChain might return dict as string like "{'backup_path': '...'}"
                            output_dict = eval(output) if output.startswith("{") else {}
                    else:
                        output_dict = output
                    
                    if isinstance(output_dict, dict) and output_dict.get("backup_path"):
                        self.reasoning_steps[-1]["backup_path"] = output_dict["backup_path"]
                except Exception as e:
                    logger.debug(f"Could not extract backup path: {str(e)}")
    
    def get_reasoning_log(self) -> List[Dict[str, Any]]:
        """Get all captured reasoning steps."""
        return self.reasoning_steps
    
    def clear(self):
        """Clear captured reasoning steps."""
        self.reasoning_steps = []


class HealerAgent:
    """Agent that diagnoses and fixes test failures."""
    
    def __init__(self, max_retries: int = 3):
        """
        Initialize the healer agent.
        
        Args:
            max_retries: Maximum number of fix attempts before rollback
        """
        self.max_retries = max_retries
        self.llm = ChatAnthropic(
            model="claude-sonnet-4-20250514",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.1  # Lower temperature for more deterministic fixes
        )
        self.callback_handler = HealerCallbackHandler()
        self.agent = self._create_agent()
        self.backup_paths: List[str] = []  # Track backups for rollback
    
    def _create_agent(self):
        """Create and configure the agent using LangChain 1.2+ API."""
        # System prompt for the agent
        system_prompt = """You are a test healing specialist. Your job is to:
1. Analyze test failures and diagnose root causes
2. Fix broken tests by adapting to API changes or correcting test logic
3. Validate fixes by running tests before finalizing

Rules:
- Only modify test files in tests/ directory
- Always validate fixes by running tests after making changes
- If a fix fails, analyze why and retry with more context
- Use backups for rollback if all attempts fail
- Be precise and minimal in your changes - only fix what's broken

Failure types to handle:
- API field renames (e.g., first_name → firstName, or firstName → name)
- Status code changes (e.g., 201 → 200, or 200 → 404)
- Endpoint changes or URL modifications
- Test logic bugs (wrong assertions, incorrect expected values)
- Environment issues (timeouts, network errors)

When diagnosing:
1. First, read the test file to understand the current test code
2. Call the API to verify the actual current behavior
3. Compare expected vs actual to identify the mismatch
4. Categorize the failure type (API change, test bug, etc.)
5. Generate a minimal fix that addresses the root cause
6. Write the fix and validate by running the test

Output your reasoning clearly:
- State your diagnosis: "Detected: [failure type] - [description]"
- Explain your actions: "Action: [what you're doing]"
- Report results: "Result: [outcome]"

Let's fix this test failure step by step."""
        
        # Create agent using new LangChain 1.2+ API
        agent = create_agent(
            model=self.llm,
            tools=ALL_TOOLS,
            system_prompt=system_prompt,
            debug=False
        )
        
        return agent
    
    def _load_failure_context(self, failure_json_path: str) -> FailureContext:
        """Load failure context from JSON file."""
        try:
            with open(failure_json_path, 'r') as f:
                data = json.load(f)
            return FailureContext(**data)
        except Exception as e:
            raise ValueError(f"Failed to load failure context: {str(e)}")
    
    def _format_failure_prompt(self, failure_context: FailureContext, attempt: int = 1) -> str:
        """Format failure context into a prompt for the agent."""
        test_failure = failure_context.test_failure
        api_response = failure_context.api_response
        
        prompt = f"""Test Failure Analysis and Fix

Test Details:
- Test File: {test_failure.test_file}
- Test Name: {test_failure.test_name}
- Error Type: {test_failure.error_type}
- Error Message: {test_failure.error_message}
- Line Number: {test_failure.line_number}

Failure Information:
- Expected: {test_failure.expected}
- Actual: {test_failure.actual}

API Response (from failed test):
- Status Code: {api_response.status_code if api_response else 'N/A'}
- Response Body: {json.dumps(api_response.body, indent=2) if api_response and api_response.body else 'N/A'}
- Request Method: {failure_context.request_method}
- Request URL: {failure_context.request_url}
"""
        
        if attempt > 1:
            prompt += f"""
Previous Fix Attempt {attempt - 1} failed. Please analyze why and try a different approach.
Consider:
- Did you correctly identify the root cause?
- Is the fix syntax correct?
- Are there other issues in the test?
- Should you verify the API response again?
"""
        
        if test_failure.traceback:
            prompt += f"""
Full Traceback:
{test_failure.traceback}
"""
        
        prompt += """
Your task:
1. Read the test file to see the current code
2. Call the API to verify current behavior (if needed)
3. Diagnose the root cause
4. Fix the test code
5. Run the test to validate the fix

Start by reading the test file."""
        
        return prompt
    
    def _log_diagnosis(self, failure_context: FailureContext):
        """Log diagnosis information."""
        test_failure = failure_context.test_failure
        print(f"\n[DIAGNOSIS] {test_failure.test_name} failed: {test_failure.error_type}")
        print(f"[DIAGNOSIS] Error: {test_failure.error_message}")
        if test_failure.expected and test_failure.actual:
            print(f"[DIAGNOSIS] Expected: {test_failure.expected}, Actual: {test_failure.actual}")
    
    def _log_reasoning_steps(self):
        """Log agent reasoning steps captured by callback handler."""
        steps = self.callback_handler.get_reasoning_log()
        for step in steps:
            if step.get("type") == "reasoning":
                content = step.get("content", "")
                # Extract key reasoning (first few lines)
                lines = content.split("\n")[:3]
                if lines:
                    print(f"[ANALYSIS] {lines[0][:100]}...")  # Truncate for readability
            elif step.get("type") == "action":
                tool = step.get("tool", "unknown")
                print(f"[ACTION] Using tool: {tool}")
    
    def _extract_decision_from_output(self, output: str) -> Optional[str]:
        """Extract decision/fix type from agent output."""
        # Look for patterns like "Detected:", "Fix type:", etc.
        lines = output.split("\n")
        for line in lines:
            if "Detected:" in line or "Fix type:" in line or "DECISION" in line.upper():
                return line.strip()
        return None
    
    def _rollback(self, backup_path: str, original_file: str) -> bool:
        """Rollback to backup file."""
        try:
            if backup_path and Path(backup_path).exists():
                # Extract original content from backup
                backup_content = Path(backup_path).read_text()
                Path(original_file).write_text(backup_content)
                print(f"[ROLLBACK] Restored {original_file} from backup")
                return True
            return False
        except Exception as e:
            logger.error(f"Rollback failed: {str(e)}")
            return False
    
    def heal_failure(self, failure_json_path: str) -> Dict[str, Any]:
        """
        Heal a test failure.
        
        Args:
            failure_json_path: Path to failure JSON file
            
        Returns:
            {
                "success": bool,
                "test_name": str,
                "attempts": int,
                "decision": str (if successful),
                "error": str (if failed)
            }
        """
        # Load failure context
        try:
            failure_context = self._load_failure_context(failure_json_path)
        except Exception as e:
            return {
                "success": False,
                "test_name": "unknown",
                "attempts": 0,
                "decision": None,
                "error": f"Failed to load failure context: {str(e)}"
            }
        
        test_failure = failure_context.test_failure
        test_file = test_failure.test_file
        test_name = test_failure.test_name
        
        # Get project root (parent of src/)
        project_root = Path(__file__).parent.parent.parent
        
        # Handle both relative and absolute paths
        test_file_path = Path(test_file)
        if test_file_path.is_absolute():
            # If absolute, make relative to project root
            try:
                test_path = f"{test_file_path.relative_to(project_root)}::{test_name}"
            except ValueError:
                # If not in project root, use as-is
                test_path = f"{test_file}::{test_name}"
        else:
            # If already relative, use as-is
            test_path = f"{test_file}::{test_name}"
        
        # Log diagnosis
        self._log_diagnosis(failure_context)
        
        # Clear previous reasoning
        self.callback_handler.clear()
        self.backup_paths = []
        
        # Retry loop
        for attempt in range(1, self.max_retries + 1):
            print(f"\n[ATTEMPT {attempt}/{self.max_retries}] Healing {test_name}...")
            
            # Format prompt with failure context
            prompt = self._format_failure_prompt(failure_context, attempt)
            
            try:
                # Run agent (new API uses invoke with messages)
                from langchain_core.messages import HumanMessage
                result = self.agent.invoke({"messages": [HumanMessage(content=prompt)]})
                
                # Extract output from result (format may vary)
                if isinstance(result, dict):
                    # Check for different possible output formats
                    if "messages" in result:
                        # Get last message content
                        messages = result["messages"]
                        if messages:
                            output = messages[-1].content if hasattr(messages[-1], 'content') else str(messages[-1])
                        else:
                            output = str(result)
                    elif "output" in result:
                        output = result["output"]
                    else:
                        output = str(result)
                else:
                    output = str(result)
                
                # Log reasoning steps
                self._log_reasoning_steps()
                
                # Extract backup paths from tool outputs
                for step in self.callback_handler.get_reasoning_log():
                    if step.get("type") == "action" and step.get("tool") == "write_test_file":
                        backup_path = step.get("backup_path")
                        if backup_path:
                            self.backup_paths.append(backup_path)
                
                # Extract decision if available
                decision = self._extract_decision_from_output(output)
                if decision:
                    print(f"[DECISION] {decision}")
                
                # Validate fix by running test
                print(f"[VALIDATION] Running {test_name}...")
                from src.agent.tools import run_single_test
                test_result = run_single_test(test_path)
                
                if test_result.get("passed"):
                    print(f"[RESULT] ✓ Test {test_name} passed after fix!")
                    return {
                        "success": True,
                        "test_name": test_name,
                        "attempts": attempt,
                        "decision": decision,
                        "error": None
                    }
                else:
                    print(f"[RESULT] ✗ Test {test_name} still failing")
                    print(f"[RESULT] Output: {test_result.get('output', '')[:200]}...")
                    
                    # If not last attempt, add more context for next try
                    if attempt < self.max_retries:
                        print(f"[RETRY] Attempt {attempt + 1} with additional context...")
                        # The next iteration will include previous attempt info in prompt
                    else:
                        # Last attempt failed - rollback
                        print(f"[ROLLBACK] All {self.max_retries} attempts failed. Rolling back...")
                        # Find backup (should be in write_test_file tool output)
                        # For now, we'll try to restore from the most recent backup
                        if self.backup_paths:
                            self._rollback(self.backup_paths[-1], test_file)
                        return {
                            "success": False,
                            "test_name": test_name,
                            "attempts": attempt,
                            "decision": decision,
                            "error": "All fix attempts failed. Rollback applied."
                        }
            
            except Exception as e:
                logger.error(f"Agent execution failed: {str(e)}", exc_info=True)
                if attempt < self.max_retries:
                    print(f"[ERROR] Attempt {attempt} failed: {str(e)}. Retrying...")
                else:
                    print(f"[ERROR] All attempts failed. Last error: {str(e)}")
                    # Try rollback
                    if self.backup_paths:
                        self._rollback(self.backup_paths[-1], test_file)
                    return {
                        "success": False,
                        "test_name": test_name,
                        "attempts": attempt,
                        "decision": None,
                        "error": f"Agent execution failed: {str(e)}"
                    }
        
        # Should not reach here, but just in case
        return {
            "success": False,
            "test_name": test_name,
            "attempts": self.max_retries,
            "decision": None,
            "error": "Max retries exceeded"
        }
