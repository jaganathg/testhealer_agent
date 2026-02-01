"""Test Generator Module - Generates critical missing tests with smart prioritization."""
import ast
import re
import logging
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage

from config.settings import ANTHROPIC_API_KEY
from src.agent.tools import read_test_file, list_test_files, run_single_test, PROJECT_ROOT

logger = logging.getLogger(__name__)

# Marker for generated tests
GENERATED_MARKER = "# GENERATED_BY_AGENT"

# Known API endpoints for JSONPlaceholder
KNOWN_ENDPOINTS = {
    "users": {
        "base": "/users",
        "methods": ["GET", "POST"],
        "with_id": "/users/{id}",
        "id_methods": ["GET", "PUT", "PATCH", "DELETE"],
        "error_cases": [
            ("GET", "/users/999", 404, "not_found"),
            ("PUT", "/users/999", 404, "not_found"),
            ("PATCH", "/users/999", 404, "not_found"),
            ("DELETE", "/users/999", 404, "not_found"),
        ]
    },
    "posts": {
        "base": "/posts",
        "methods": ["GET", "POST"],
        "with_id": "/posts/{id}",
        "id_methods": ["GET", "PUT", "PATCH", "DELETE"],
        "nested": "/posts/{id}/comments",
        "error_cases": [
            ("GET", "/posts/999", 404, "not_found"),
            ("PUT", "/posts/999", 404, "not_found"),
            ("DELETE", "/posts/999", 404, "not_found"),
        ]
    },
    "comments": {
        "base": "/comments",
        "methods": ["GET"],
        "with_id": "/comments/{id}",
        "id_methods": ["GET"],
        "error_cases": [
            ("GET", "/comments/999", 404, "not_found"),
        ]
    },
    "albums": {
        "base": "/albums",
        "methods": ["GET", "POST"],
        "with_id": "/albums/{id}",
        "id_methods": ["GET", "PUT", "PATCH", "DELETE"],
        "error_cases": [
            ("GET", "/albums/999", 404, "not_found"),
        ]
    },
    "photos": {
        "base": "/photos",
        "methods": ["GET", "POST"],
        "with_id": "/photos/{id}",
        "id_methods": ["GET", "PUT", "PATCH", "DELETE"],
        "error_cases": [
            ("GET", "/photos/999", 404, "not_found"),
        ]
    },
    "todos": {
        "base": "/todos",
        "methods": ["GET", "POST"],
        "with_id": "/todos/{id}",
        "id_methods": ["GET", "PUT", "PATCH", "DELETE"],
        "error_cases": [
            ("GET", "/todos/999", 404, "not_found"),
        ]
    },
}


class Generator:
    """Generates critical missing tests with smart prioritization."""
    
    def __init__(self, max_generations: int = 5):
        """
        Initialize test generator.
        
        Args:
            max_generations: Maximum number of tests to generate per run
        """
        self.max_generations = max_generations
        self.llm = ChatAnthropic(
            model="claude-3-5-sonnet-20241022",
            api_key=ANTHROPIC_API_KEY,
            temperature=0.2  # Low temperature for consistent test generation
        )
        self.tests_dir = PROJECT_ROOT / "tests" / "api"
    
    def _parse_existing_tests(self) -> Dict[str, Set[str]]:
        """
        Parse existing test files to understand what's covered.
        
        Returns:
            Dict mapping endpoint patterns to set of test types covered
            Example: {"/users/{id}": {"GET", "PUT", "DELETE"}, ...}
        """
        coverage = {}
        
        try:
            result = list_test_files()
            if not result.get("success"):
                logger.warning("Could not list test files")
                return coverage
            
            for test_file_path in result.get("files", []):
                try:
                    file_result = read_test_file(test_file_path)
                    if not file_result.get("success"):
                        continue
                    
                    content = file_result.get("content", "")
                    
                    # Skip generated tests
                    if GENERATED_MARKER in content:
                        continue
                    
                    # Parse test file to extract endpoint patterns
                    self._extract_coverage_from_content(content, coverage)
                    
                except Exception as e:
                    logger.debug(f"Error parsing {test_file_path}: {e}")
        
        except Exception as e:
            logger.error(f"Error parsing existing tests: {e}")
        
        return coverage
    
    def _extract_coverage_from_content(self, content: str, coverage: Dict[str, Set[str]]):
        """Extract endpoint coverage from test file content."""
        # Look for URL patterns in test code
        # Pattern: client.get(f"{BASE_URL}/users/1")
        # Pattern: client.post(f"{BASE_URL}/users", json=...)
        
        # Extract all API calls
        patterns = [
            (r'client\.(get|post|put|patch|delete)\s*\([^)]*["\']([^"\']+)["\']', "method_url"),
            (r'f"{BASE_URL}([^"]+)"', "url_only"),
        ]
        
        for pattern, pattern_type in patterns:
            matches = re.finditer(pattern, content, re.IGNORECASE)
            for match in matches:
                if pattern_type == "method_url":
                    method = match.group(1).upper()
                    url = match.group(2)
                else:
                    # Try to infer method from context (simplified)
                    method = "GET"  # Default
                    url = match.group(1)
                
                # Normalize URL (remove IDs, make pattern)
                normalized = self._normalize_endpoint(url)
                if normalized:
                    if normalized not in coverage:
                        coverage[normalized] = set()
                    coverage[normalized].add(method)
    
    def _normalize_endpoint(self, url: str) -> Optional[str]:
        """Normalize endpoint URL to pattern (e.g., /users/1 -> /users/{id})."""
        # Remove base URL if present
        url = url.replace("https://jsonplaceholder.typicode.com", "")
        url = url.strip("/")
        
        # Replace numeric IDs with {id}
        url = re.sub(r'/\d+', '/{id}', url)
        
        # Return with leading slash
        return f"/{url}" if url else None
    
    def _identify_gaps(self, coverage: Dict[str, Set[str]]) -> List[Dict[str, Any]]:
        """
        Identify critical test gaps based on priority rules.
        
        Priority:
        1. Error responses (4xx, 5xx) - highest
        2. Authentication edge cases
        3. Data mutation endpoints (POST, PUT, DELETE)
        4. Required field validation
        5. Skip: duplicate happy-path, trivial GETs already covered
        """
        gaps = []
        
        for resource, endpoint_info in KNOWN_ENDPOINTS.items():
            # Check error cases (highest priority)
            for method, url_pattern, expected_status, test_type in endpoint_info.get("error_cases", []):
                normalized = self._normalize_endpoint(url_pattern)
                if normalized:
                    # Check if this error case is already tested
                    test_key = f"{normalized}::{test_type}"
                    if normalized not in coverage or test_type not in str(coverage.get(normalized, set())):
                        gaps.append({
                            "priority": 1,  # Highest priority
                            "resource": resource,
                            "method": method,
                            "url_pattern": url_pattern,
                            "test_type": test_type,
                            "expected_status": expected_status,
                            "description": f"{method} {url_pattern} should return {expected_status}"
                        })
            
            # Check mutation endpoints (POST, PUT, DELETE) for validation errors
            if "POST" in endpoint_info.get("methods", []):
                normalized = self._normalize_endpoint(endpoint_info["base"])
                if normalized not in coverage or "POST" not in coverage.get(normalized, set()):
                    # Check if validation error test exists
                    gaps.append({
                        "priority": 2,
                        "resource": resource,
                        "method": "POST",
                        "url_pattern": endpoint_info["base"],
                        "test_type": "validation_error",
                        "expected_status": 400,
                        "description": f"POST {endpoint_info['base']} with invalid/missing required fields"
                    })
        
        # Sort by priority (lower number = higher priority)
        gaps.sort(key=lambda x: x["priority"])
        
        # Limit to max_generations
        return gaps[:self.max_generations]
    
    def _check_duplicate(self, test_content: str, existing_tests: List[str]) -> bool:
        """
        Check if generated test is similar to existing tests.
        
        Returns:
            True if duplicate/similar test exists
        """
        # Extract test function name and key assertions
        test_name_match = re.search(r'def\s+(test_\w+)', test_content)
        if not test_name_match:
            return False
        
        new_test_name = test_name_match.group(1)
        
        # Check if test name already exists
        for existing_content in existing_tests:
            if new_test_name in existing_content:
                return True
        
        # Extract URL pattern from new test
        url_match = re.search(r'f"{BASE_URL}([^"]+)"', test_content)
        if url_match:
            new_url = self._normalize_endpoint(url_match.group(1))
            
            # Check if same URL pattern exists in existing tests
            for existing_content in existing_tests:
                existing_urls = re.findall(r'f"{BASE_URL}([^"]+)"', existing_content)
                for existing_url in existing_urls:
                    if self._normalize_endpoint(existing_url) == new_url:
                        # Check if same method
                        new_method = re.search(r'client\.(\w+)\(', test_content)
                        existing_method = re.search(r'client\.(\w+)\(', existing_content)
                        if new_method and existing_method:
                            if new_method.group(1).upper() == existing_method.group(1).upper():
                                return True
        
        return False
    
    def _get_existing_test_examples(self) -> str:
        """Get examples of existing test structure for LLM to match."""
        examples = []
        
        try:
            result = list_test_files()
            if not result.get("success"):
                return ""
            
            # Get first 2-3 non-generated test files
            for test_file_path in result.get("files", [])[:3]:
                try:
                    file_result = read_test_file(test_file_path)
                    if file_result.get("success"):
                        content = file_result.get("content", "")
                        # Skip generated tests
                        if GENERATED_MARKER not in content:
                            examples.append(content[:1000])  # First 1000 chars
                except:
                    pass
        except:
            pass
        
        return "\n\n---\n\n".join(examples) if examples else ""
    
    def _generate_test_code(self, gap: Dict[str, Any]) -> Optional[str]:
        """Generate test code for a gap using LLM."""
        existing_examples = self._get_existing_test_examples()
        
        prompt = f"""You are a test generation specialist. Generate a new test case that matches the EXACT structure and format of existing tests.

EXISTING TEST EXAMPLES (match this format exactly):
{existing_examples}

REQUIREMENTS:
1. Match the EXACT structure: imports, BASE_URL constant, docstring format, assertion style
2. Use the same `client` fixture (pytest fixture)
3. Follow the same naming convention: test_{{description}}
4. Use the same assertion patterns
5. Add docstring in the same style
6. Include the marker comment at the very top: {GENERATED_MARKER}

TEST TO GENERATE:
- Resource: {gap['resource']}
- Method: {gap['method']}
- URL Pattern: {gap['url_pattern']}
- Test Type: {gap['test_type']}
- Expected Status: {gap['expected_status']}
- Description: {gap['description']}

Generate ONLY the test function code (not the entire file). The test should:
- Test the error case or validation scenario
- Assert the correct status code
- Follow the exact same code style as the examples
- Include the marker comment `{GENERATED_MARKER}` as the first line (before the function)

IMPORTANT: Start your response with the marker comment on the first line, then the test function definition. Example:
{GENERATED_MARKER}
def test_example(client):
    \"\"\"Test description.\"\"\"
    # test code here"""

        try:
            response = self.llm.invoke([HumanMessage(content=prompt)])
            content = response.content if hasattr(response, 'content') else str(response)
            
            # Ensure marker is at the top
            if GENERATED_MARKER not in content:
                content = f"{GENERATED_MARKER}\n{content}"
            
            return content.strip()
        except Exception as e:
            logger.error(f"Error generating test code: {e}")
            return None
    
    def _validate_test_syntax(self, test_code: str) -> bool:
        """Validate that generated test code has valid Python syntax."""
        try:
            ast.parse(test_code)
            return True
        except SyntaxError as e:
            logger.warning(f"Generated test has syntax error: {e}")
            return False
    
    def _add_test_to_file(self, test_code: str, resource: str) -> Tuple[bool, Optional[str]]:
        """
        Add generated test to appropriate test file.
        
        Returns:
            (success, file_path)
        """
        # Determine target file based on resource
        file_mapping = {
            "users": "test_users.py",
            "posts": "test_auth.py",  # Posts are in test_auth.py
            "comments": "test_resources.py",
            "albums": "test_resources.py",
            "photos": "test_resources.py",
            "todos": "test_resources.py",
        }
        
        target_file = file_mapping.get(resource, "test_resources.py")
        file_path = self.tests_dir / target_file
        
        try:
            # Read existing file
            if file_path.exists():
                existing_content = file_path.read_text(encoding="utf-8")
            else:
                # Create new file with base structure
                existing_content = f'''"""BRITTLE tests for JSONPlaceholder {resource} endpoints."""
import pytest
import httpx

BASE_URL = "https://jsonplaceholder.typicode.com"

'''
            
            # Check for duplicates
            if self._check_duplicate(test_code, [existing_content]):
                logger.info(f"Duplicate test detected, skipping")
                return False, None
            
            # Extract just the test function from generated code
            # Ensure marker is included as comment before function
            test_function = test_code
            if test_function.startswith(GENERATED_MARKER):
                # Keep marker as comment
                lines = test_function.split("\n")
                if lines[0].strip() == GENERATED_MARKER:
                    # Marker is already there, keep it
                    test_function = "\n".join(lines).strip()
                else:
                    # Add marker if not present
                    test_function = f"{GENERATED_MARKER}\n{test_function}"
            else:
                # Add marker before function
                test_function = f"{GENERATED_MARKER}\n{test_function}"
            
            # Add test to file
            new_content = existing_content.rstrip() + "\n\n" + test_function + "\n"
            
            # Write file
            file_path.write_text(new_content, encoding="utf-8")
            
            return True, str(file_path.relative_to(PROJECT_ROOT))
        
        except Exception as e:
            logger.error(f"Error adding test to file: {e}")
            return False, None
    
    def generate_tests(self) -> List[Dict[str, Any]]:
        """
        Generate critical missing tests.
        
        Returns:
            List of generation results:
            [
                {
                    "success": bool,
                    "test_name": str,
                    "file_path": str,
                    "description": str,
                    "error": str (if failed)
                },
                ...
            ]
        """
        results = []
        
        print("\n[TEST GENERATOR] Analyzing test coverage...")
        
        # Parse existing tests
        coverage = self._parse_existing_tests()
        print(f"[TEST GENERATOR] Found {len(coverage)} endpoint patterns covered")
        
        # Identify gaps
        gaps = self._identify_gaps(coverage)
        print(f"[TEST GENERATOR] Identified {len(gaps)} critical gaps")
        
        if not gaps:
            print("[TEST GENERATOR] No critical gaps found. Test suite is well-covered!")
            return results
        
        # Get all existing test content for duplicate checking
        existing_tests_content = []
        try:
            list_result = list_test_files()
            if list_result.get("success"):
                for test_file in list_result.get("files", []):
                    file_result = read_test_file(test_file)
                    if file_result.get("success"):
                        existing_tests_content.append(file_result.get("content", ""))
        except:
            pass
        
        # Generate tests for each gap
        for i, gap in enumerate(gaps, 1):
            print(f"\n[GENERATION {i}/{len(gaps)}] {gap['description']}")
            
            # Generate test code
            test_code = self._generate_test_code(gap)
            if not test_code:
                results.append({
                    "success": False,
                    "test_name": f"test_{gap['test_type']}",
                    "file_path": None,
                    "description": gap["description"],
                    "error": "Failed to generate test code"
                })
                continue
            
            # Validate syntax
            if not self._validate_test_syntax(test_code):
                results.append({
                    "success": False,
                    "test_name": f"test_{gap['test_type']}",
                    "file_path": None,
                    "description": gap["description"],
                    "error": "Generated test has syntax errors"
                })
                continue
            
            # Add to file
            success, file_path = self._add_test_to_file(test_code, gap["resource"])
            if not success:
                results.append({
                    "success": False,
                    "test_name": f"test_{gap['test_type']}",
                    "file_path": file_path,
                    "description": gap["description"],
                    "error": "Failed to add test to file (duplicate or file error)"
                })
                continue
            
            # Extract test name
            test_name_match = re.search(r'def\s+(test_\w+)', test_code)
            test_name = test_name_match.group(1) if test_name_match else f"test_{gap['test_type']}"
            
            # Validate by running test
            test_path = f"{file_path}::{test_name}"
            print(f"[VALIDATION] Running {test_name}...")
            test_result = run_single_test(test_path)
            
            if test_result.get("passed"):
                print(f"[RESULT] ✓ Test {test_name} generated and passed!")
                results.append({
                    "success": True,
                    "test_name": test_name,
                    "file_path": file_path,
                    "description": gap["description"],
                    "error": None
                })
            else:
                # Test failed - remove it
                print(f"[RESULT] ✗ Test {test_name} failed. Removing...")
                try:
                    # Read file, remove the test function, write back
                    file_content = Path(PROJECT_ROOT / file_path).read_text(encoding="utf-8")
                    
                    # Find and remove the test function (from marker to next def or end of file)
                    lines = file_content.split("\n")
                    new_lines = []
                    skip_until_next_def = False
                    
                    for i, line in enumerate(lines):
                        if GENERATED_MARKER in line:
                            # Found marker - skip this and following lines until next def or end
                            skip_until_next_def = True
                            continue
                        
                        if skip_until_next_def:
                            # Check if this is the start of a new function (not our test)
                            if line.strip().startswith("def ") and not line.strip().startswith(f"def {test_name}("):
                                skip_until_next_def = False
                                new_lines.append(line)
                            # If it's our test function, skip it
                            elif line.strip().startswith(f"def {test_name}("):
                                # Skip until next def or end
                                continue
                            # Skip lines until we find next def
                            elif not line.strip().startswith("def "):
                                continue
                            else:
                                skip_until_next_def = False
                                new_lines.append(line)
                        else:
                            new_lines.append(line)
                    
                    # Write back cleaned content
                    cleaned_content = "\n".join(new_lines).rstrip() + "\n"
                    Path(PROJECT_ROOT / file_path).write_text(cleaned_content, encoding="utf-8")
                    print(f"[CLEANUP] Removed failed test from {file_path}")
                except Exception as e:
                    logger.warning(f"Error removing failed test: {e}")
                
                results.append({
                    "success": False,
                    "test_name": test_name,
                    "file_path": file_path,
                    "description": gap["description"],
                    "error": f"Test failed validation: {test_result.get('output', '')[:100]}"
                })
        
        return results
