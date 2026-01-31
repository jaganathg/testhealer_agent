"""Script to prepare test files for demo by removing FRAGILE/BRITTLE comments."""
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TESTS_DIR = PROJECT_ROOT / "tests" / "api"
BACKUP_DIR = PROJECT_ROOT / "failures" / ".backups" / ".original_tests"


def remove_fragile_comments(content: str) -> str:
    """
    Remove FRAGILE and BRITTLE comments from test files.
    
    This makes the demo more realistic - agent must diagnose without hints.
    """
    lines = content.split("\n")
    cleaned_lines = []
    
    for line in lines:
        # Remove lines with FRAGILE or BRITTLE comments
        if "# FRAGILE:" in line or "# BRITTLE:" in line:
            # Check if it's a standalone comment or inline
            stripped = line.strip()
            if stripped.startswith("#"):
                # Standalone comment line - skip it
                continue
            else:
                # Inline comment - remove the comment part
                if "# FRAGILE:" in line:
                    line = line.split("# FRAGILE:")[0].rstrip()
                if "# BRITTLE:" in line:
                    line = line.split("# BRITTLE:")[0].rstrip()
        
        cleaned_lines.append(line)
    
    return "\n".join(cleaned_lines)


def backup_original_tests():
    """Backup original test files before removing comments."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    for test_file in TESTS_DIR.glob("test_*.py"):
        backup_path = BACKUP_DIR / test_file.name
        backup_path.write_text(test_file.read_text())
        print(f"Backed up: {test_file.name} -> {backup_path}")


def restore_original_tests():
    """Restore original test files from backup."""
    if not BACKUP_DIR.exists():
        print("No backup found. Original files not modified.")
        return
    
    for backup_file in BACKUP_DIR.glob("test_*.py"):
        original_path = TESTS_DIR / backup_file.name
        original_path.write_text(backup_file.read_text())
        print(f"Restored: {backup_file.name} -> {original_path}")


def prepare_for_demo():
    """Remove FRAGILE/BRITTLE comments from all test files."""
    # First backup originals
    backup_original_tests()
    
    # Then remove comments
    for test_file in TESTS_DIR.glob("test_*.py"):
        content = test_file.read_text()
        cleaned = remove_fragile_comments(content)
        test_file.write_text(cleaned)
        print(f"Prepared for demo: {test_file.name}")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "prepare":
            print("Preparing test files for demo (removing FRAGILE/BRITTLE comments)...")
            prepare_for_demo()
            print("\n✓ Test files ready for demo. Originals backed up in failures/.backups/.original_tests/")
        
        elif command == "restore":
            print("Restoring original test files...")
            restore_original_tests()
            print("\n✓ Original test files restored.")
        
        else:
            print("Commands: prepare, restore")
    else:
        print("Demo Test Preparation Script")
        print("\nUsage:")
        print("  python scripts/prepare_demo_tests.py prepare  # Remove comments for demo")
        print("  python scripts/prepare_demo_tests.py restore  # Restore original files")
