"""Cleanup script to remove LLM-generated test files for demo purposes."""
import sys
from pathlib import Path

# Project root (parent of scripts/)
PROJECT_ROOT = Path(__file__).parent.parent
TESTS_DIR = PROJECT_ROOT / "tests" / "api"
GENERATED_MARKER = "# GENERATED_BY_AGENT"


def find_files_with_generated_tests() -> list[Path]:
    """Find all test files containing the generated marker."""
    files_with_generated = []
    
    if not TESTS_DIR.exists():
        print(f"Tests directory not found: {TESTS_DIR}")
        return files_with_generated
    
    # Search all Python files in tests/api/
    for test_file in TESTS_DIR.glob("test_*.py"):
        try:
            content = test_file.read_text(encoding="utf-8")
            if GENERATED_MARKER in content:
                files_with_generated.append(test_file)
        except Exception as e:
            print(f"Error reading {test_file}: {e}")
    
    return files_with_generated


def remove_generated_tests_from_file(file_path: Path) -> int:
    """
    Remove all generated test functions from a file.
    
    Returns:
        Number of test functions removed
    """
    import re
    
    try:
        content = file_path.read_text(encoding="utf-8")
        
        # Check original file ending from git (more reliable than current file state)
        # This ensures we restore to the actual committed state
        import subprocess
        original_has_newline = False
        try:
            # Get original file content from git
            result = subprocess.run(
                ["git", "show", f"HEAD:{file_path.relative_to(PROJECT_ROOT)}"],
                capture_output=True,
                text=True,
                cwd=PROJECT_ROOT,
                timeout=5
            )
            if result.returncode == 0:
                original_has_newline = result.stdout.endswith("\n")
        except Exception:
            # Fallback: use current file state (might not be accurate if file was modified)
            original_has_newline = content.endswith("\n")
        
        lines = content.split("\n")
        new_lines = []
        skip_section = False
        removed_count = 0
        i = 0
        
        while i < len(lines):
            line = lines[i]
            
            # Check for marker - start skipping
            if GENERATED_MARKER in line:
                skip_section = True
                # Remove trailing blank lines before marker (if any)
                while new_lines and not new_lines[-1].strip():
                    new_lines.pop()
                # Skip the marker line itself
                i += 1
                continue
            
            if skip_section:
                # Check if this is a function definition (end of previous function)
                stripped = line.strip()
                if stripped.startswith("def ") and not stripped.startswith("def test_"):
                    # New non-test function, stop skipping
                    skip_section = False
                    new_lines.append(line)
                elif stripped.startswith("def test_"):
                    # This is the generated test function - skip it and its body
                    removed_count += 1
                    # Skip until we find next def or end of file
                    i += 1
                    # Track indentation to know when function ends
                    if i < len(lines):
                        # Find base indentation of function body
                        base_indent = 0
                        if i < len(lines) and lines[i].strip():
                            base_indent = len(lines[i]) - len(lines[i].lstrip())
                        
                        # Skip all lines with same or greater indentation
                        while i < len(lines):
                            current_line = lines[i]
                            if not current_line.strip():
                                # Empty line, keep going
                                i += 1
                                continue
                            
                            current_indent = len(current_line) - len(current_line.lstrip())
                            # If we hit a line with less indentation (or def at start), stop
                            if current_indent < base_indent or (current_indent == 0 and current_line.strip().startswith("def ")):
                                break
                            i += 1
                    continue
                else:
                    # Still in function body, skip
                    i += 1
                    continue
            else:
                # Normal line, keep it
                new_lines.append(line)
                i += 1
        
        # Write cleaned content
        cleaned_content = "\n".join(new_lines)
        # Remove excessive blank lines (more than 2 consecutive)
        cleaned_content = re.sub(r'\n{3,}', '\n\n', cleaned_content)
        
        # Remove trailing blank lines (but preserve original newline style)
        # Only strip if we're removing blank lines, not the final newline
        if original_has_newline:
            # Original had newline - preserve it, but remove trailing blank lines
            cleaned_content = cleaned_content.rstrip() + "\n"
        else:
            # Original had no newline - remove all trailing whitespace including newlines
            cleaned_content = cleaned_content.rstrip()
        
        file_path.write_text(cleaned_content, encoding="utf-8")
        
        return removed_count
    
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return 0


def cleanup_generated_tests(dry_run: bool = False) -> int:
    """
    Remove all generated test functions from test files.
    
    Args:
        dry_run: If True, only show what would be removed without removing
        
    Returns:
        Number of test functions removed
    """
    files_with_generated = find_files_with_generated_tests()
    
    if not files_with_generated:
        print("No files with generated tests found.")
        return 0
    
    print(f"Found {len(files_with_generated)} file(s) with generated tests:")
    for file in files_with_generated:
        print(f"  - {file.relative_to(PROJECT_ROOT)}")
    
    if dry_run:
        print("\n[DRY RUN] Would remove generated tests from these files. Run without --dry-run to remove.")
        return len(files_with_generated)
    
    # Remove generated tests from files
    total_removed = 0
    for file in files_with_generated:
        removed = remove_generated_tests_from_file(file)
        if removed > 0:
            print(f"Removed {removed} generated test(s) from {file.relative_to(PROJECT_ROOT)}")
            total_removed += removed
    
    print(f"\n✓ Cleanup complete: {total_removed} generated test function(s) removed.")
    return total_removed


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Cleanup LLM-generated test files")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be deleted without actually deleting"
    )
    
    args = parser.parse_args()
    
    try:
        count = cleanup_generated_tests(dry_run=args.dry_run)
        sys.exit(0 if count >= 0 else 1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
