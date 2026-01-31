"""Pytest configuration and hooks for failure capture."""
import json
import re
import traceback
from pathlib import Path
from typing import Dict, Optional, Any
import pytest
import httpx
from src.analyzer.failure_parser import FailureContext, TestFailure, APIResponse


# Global storage for test context (request/response data)
_test_context: Dict[str, Dict[str, Any]] = {}


class TrackingClient:
    """HTTP client wrapper that tracks requests and responses."""
    
    def __init__(self, base_client: httpx.Client, test_node_id: str):
        self._client = base_client
        self._test_node_id = test_node_id
        self._last_request: Optional[Dict[str, Any]] = None
        self._last_response: Optional[httpx.Response] = None
    
    def _make_request(self, method: str, *args, **kwargs):
        """Internal method to make request and track it."""
        url = args[0] if args else kwargs.get('url', '')
        payload = kwargs.get('json') or kwargs.get('data')
        
        self._last_request = {
            'method': method,
            'url': str(url),
            'payload': payload
        }
        
        # Store request data immediately (even if request fails)
        _test_context[self._test_node_id] = {
            'request': self._last_request,
            'response': None  # Will be updated if request succeeds
        }
        
        # Make request using the base client's method
        try:
            if method == 'GET':
                response = self._client.get(*args, **kwargs)
            elif method == 'POST':
                response = self._client.post(*args, **kwargs)
            elif method == 'PUT':
                response = self._client.put(*args, **kwargs)
            elif method == 'PATCH':
                response = self._client.patch(*args, **kwargs)
            elif method == 'DELETE':
                response = self._client.delete(*args, **kwargs)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            self._last_response = response
            
            # Store response data in context
            try:
                # Read response content now while response is still valid
                try:
                    body = response.json()
                except (ValueError, AttributeError):
                    try:
                        body = response.text
                    except:
                        body = None
                
                _test_context[self._test_node_id]['response'] = {
                    'status_code': response.status_code,
                    'body': body,
                    'headers': dict(response.headers),
                    'url': str(response.url)
                }
            except Exception as e:
                # If storing fails, at least keep the response object
                _test_context[self._test_node_id]['response_object'] = response
            
            return response
            
        except Exception as e:
            # Request failed - store error info but keep request data
            _test_context[self._test_node_id]['error'] = {
                'type': type(e).__name__,
                'message': str(e)
            }
            raise  # Re-raise the exception
    
    def get(self, *args, **kwargs):
        """GET request with tracking."""
        return self._make_request('GET', *args, **kwargs)
    
    def post(self, *args, **kwargs):
        """POST request with tracking."""
        return self._make_request('POST', *args, **kwargs)
    
    def put(self, *args, **kwargs):
        """PUT request with tracking."""
        return self._make_request('PUT', *args, **kwargs)
    
    def patch(self, *args, **kwargs):
        """PATCH request with tracking."""
        return self._make_request('PATCH', *args, **kwargs)
    
    def delete(self, *args, **kwargs):
        """DELETE request with tracking."""
        return self._make_request('DELETE', *args, **kwargs)
    
    def __getattr__(self, name):
        """Delegate other attributes to underlying client."""
        return getattr(self._client, name)
    
    def get_last_request(self) -> Optional[Dict[str, Any]]:
        """Get last request details."""
        return self._last_request
    
    def get_last_response(self) -> Optional[httpx.Response]:
        """Get last response."""
        return self._last_response


@pytest.fixture
def client(request):
    """HTTP client fixture with request/response tracking."""
    base_client = httpx.Client(timeout=10.0)
    test_node_id = request.node.nodeid
    tracking_client = TrackingClient(base_client, test_node_id)
    
    yield tracking_client
    
    # Cleanup - but keep context data for hook to access
    base_client.close()
    # Don't delete context here - let it persist for the hook
    # It will be cleaned up naturally or can be cleaned in a session hook


def _extract_assertion_details(error_message: str) -> tuple[Optional[Any], Optional[Any]]:
    """Extract actual and expected values from assertion error message."""
    actual = None
    expected = None
    
    # Pattern 1: assert x == y -> "assert 1 == 2"
    match = re.search(r'assert\s+(.+?)\s*==\s*(.+)', error_message)
    if match:
        actual = match.group(1).strip()
        expected = match.group(2).strip()
    
    # Pattern 2: assert x in y -> "assert 'key' in dict"
    match = re.search(r"assert\s+['\"](.+?)['\"]\s+in\s+", error_message)
    if match:
        expected = match.group(1)
    
    # Pattern 3: assert len(x) == y -> "assert len(data) == 12"
    match = re.search(r'assert\s+len\([^)]+\)\s*==\s*(\d+)', error_message)
    if match:
        expected = int(match.group(1))
    
    # Pattern 4: assert x["key"] == y -> field access
    match = re.search(r"assert\s+\w+\[['\"](.+?)['\"]\]\s*==\s*(.+)", error_message)
    if match:
        expected = match.group(2).strip().strip('"').strip("'")
    
    return actual, expected


def _parse_assertion_error(exc_info) -> tuple[str, Optional[Any], Optional[Any]]:
    """Parse assertion error to extract error message, actual, and expected."""
    error_type = exc_info[0].__name__ if exc_info[0] else "Exception"
    error_message = str(exc_info[1]) if exc_info[1] else ""
    
    # Try to extract from traceback
    tb_lines = traceback.format_exception(*exc_info)
    full_traceback = "".join(tb_lines)
    
    # Look for assertion details in traceback
    actual, expected = _extract_assertion_details(error_message)
    
    # If not found, try parsing traceback
    if actual is None or expected is None:
        for line in tb_lines:
            actual, expected = _extract_assertion_details(line)
            if actual or expected:
                break
    
    return error_message, actual, expected


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """Capture test results and failures."""
    outcome = yield
    report = outcome.get_result()
    
    # Only process failures
    if report.when == "call" and report.failed:
        test_node_id = item.nodeid
        test_file = str(item.fspath) if hasattr(item, 'fspath') else str(item.path)
        test_name = item.name
        
        # Get exception info
        exc_info = call.excinfo
        if not exc_info:
            return
        
        # Parse assertion error - excinfo is ExceptionInfo tuple-like object
        exc_tuple = (exc_info.type, exc_info.value, exc_info.tb)
        error_message, actual, expected = _parse_assertion_error(exc_tuple)
        error_type = exc_info.type.__name__ if exc_info.type else "Exception"
        
        # Get full traceback
        tb_lines = traceback.format_exception(*exc_tuple)
        full_traceback = "".join(tb_lines)
        
        # Try to extract line number from traceback
        line_number = None
        for line in tb_lines:
            match = re.search(r'File "([^"]+)", line (\d+)', line)
            if match and test_file in match.group(1):
                line_number = int(match.group(2))
                break
        
        # Create TestFailure
        test_failure = TestFailure(
            test_file=test_file,
            test_name=test_name,
            error_type=error_type,
            error_message=error_message,
            actual=actual,
            expected=expected,
            line_number=line_number,
            traceback=full_traceback
        )
        
        # Get API response if available
        api_response = None
        request_method = None
        request_url = None
        request_payload = None
        
        if test_node_id in _test_context:
            context_data = _test_context[test_node_id]
            
            # Check if we have pre-stored response data
            if 'response' in context_data and context_data['response'] is not None:
                resp_data = context_data['response']
                api_response = APIResponse(
                    status_code=resp_data['status_code'],
                    body=resp_data['body'],
                    headers=resp_data['headers'],
                    url=resp_data['url']
                )
            elif 'response_object' in context_data:
                # Fallback: try to read from response object
                last_response = context_data['response_object']
                try:
                    try:
                        body = last_response.json()
                    except (ValueError, AttributeError):
                        try:
                            body = last_response.text
                        except:
                            body = None
                    
                    api_response = APIResponse(
                        status_code=last_response.status_code,
                        body=body,
                        headers=dict(last_response.headers),
                        url=str(last_response.url)
                    )
                except Exception:
                    pass
            
            # Get request data
            if 'request' in context_data:
                last_request = context_data['request']
                request_method = last_request.get('method')
                request_url = last_request.get('url')
                request_payload = last_request.get('payload')
        
        # Create FailureContext
        failure_context = FailureContext(
            test_failure=test_failure,
            api_response=api_response,
            request_method=request_method,
            request_url=request_url,
            request_payload=request_payload
        )
        
        # Write to JSON file
        output_dir = Path("failures")
        output_dir.mkdir(exist_ok=True)
        
        # Sanitize test name for filename
        safe_test_name = re.sub(r'[^\w\-_]', '_', test_name)
        output_file = output_dir / f"{safe_test_name}_{item.nodeid.replace('::', '_').replace('/', '_')}.json"
        
        with open(output_file, 'w') as f:
            f.write(failure_context.to_json())
        
        print(f"\n[FAILURE CAPTURED] {test_name} -> {output_file}")