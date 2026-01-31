"""Failure analysis models and parsing utilities."""
from datetime import datetime
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    """Captured HTTP response data."""
    status_code: int
    body: Any = Field(default=None, description="Response body (parsed JSON or raw text)")
    headers: Dict[str, str] = Field(default_factory=dict)
    url: str = Field(default="", description="Request URL")


class TestFailure(BaseModel):
    """Test failure metadata."""
    test_file: str = Field(description="Path to test file")
    test_name: str = Field(description="Test function name")
    error_type: str = Field(description="Exception type (e.g., AssertionError)")
    error_message: str = Field(description="Error message")
    actual: Optional[Any] = Field(default=None, description="Actual value from assertion")
    expected: Optional[Any] = Field(default=None, description="Expected value from assertion")
    line_number: Optional[int] = Field(default=None, description="Line number where failure occurred")
    traceback: Optional[str] = Field(default=None, description="Full traceback")


class FailureContext(BaseModel):
    """Complete failure context for agent analysis."""
    test_failure: TestFailure
    api_response: Optional[APIResponse] = Field(default=None)
    request_method: Optional[str] = Field(default=None, description="HTTP method (GET, POST, etc.)")
    request_url: Optional[str] = Field(default=None)
    request_payload: Optional[Any] = Field(default=None, description="Request body/payload")
    timestamp: str = Field(default_factory=lambda: datetime.now().isoformat())
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return self.model_dump()
    
    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        import json
        return json.dumps(self.to_dict(), indent=indent, default=str)