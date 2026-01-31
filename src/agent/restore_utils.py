"""Utility functions to restore original test files from backups."""
import json
from pathlib import Path
from typing import List, Dict, Optional
from datetime import datetime

PROJECT_ROOT = Path(__file__).parent.parent.parent
BACKUP_DIR = PROJECT_ROOT / "failures" / ".backups"
TESTS_DIR = PROJECT_ROOT / "tests" / "api"


def list_backups(test_file_name: Optional[str] = None) -> List[Dict[str, str]]:
    """
    List all available backups.
    
    Args:
        test_file_name: Optional filter by test file name (e.g., "test_users")
    
    Returns:
        List of backup info dicts with: backup_path, original_file, timestamp
    """
    if not BACKUP_DIR.exists():
        return []
    
    backups = []
    for backup_file in BACKUP_DIR.glob("*.backup.*.py"):
        # Parse: test_users.backup.20260130_123456.py
        parts = backup_file.stem.split(".backup.")
        if len(parts) == 2:
            original_name = parts[0]
            timestamp_str = parts[1]
            
            # Filter if test_file_name specified
            if test_file_name and test_file_name not in original_name:
                continue
            
            # Find original file
            original_file = TESTS_DIR / f"{original_name}.py"
            
            backups.append({
                "backup_path": str(backup_file),
                "original_file": str(original_file),
                "test_file": f"{original_name}.py",
                "timestamp": timestamp_str,
                "backup_name": backup_file.name
            })
    
    # Sort by timestamp (newest first)
    backups.sort(key=lambda x: x["timestamp"], reverse=True)
    return backups


def restore_from_backup(backup_path: str, original_file: Optional[str] = None) -> Dict[str, Any]:
    """
    Restore a test file from backup.
    
    Args:
        backup_path: Path to backup file
        original_file: Optional original file path (auto-detected if not provided)
    
    Returns:
        {
            "success": bool,
            "restored_file": str,
            "backup_path": str,
            "error": str (if failed)
        }
    """
    try:
        backup = Path(backup_path)
        if not backup.exists():
            return {
                "success": False,
                "restored_file": None,
                "backup_path": backup_path,
                "error": f"Backup file not found: {backup_path}"
            }
        
        # Auto-detect original file if not provided
        if not original_file:
            # Parse backup name: test_users.backup.20260130_123456.py
            parts = backup.stem.split(".backup.")
            if len(parts) == 2:
                original_name = parts[0]
                original_file = str(TESTS_DIR / f"{original_name}.py")
            else:
                return {
                    "success": False,
                    "restored_file": None,
                    "backup_path": backup_path,
                    "error": f"Could not parse backup filename: {backup.name}"
                }
        
        original = Path(original_file)
        
        # Ensure original file is in tests/ directory
        if not str(original).startswith(str(TESTS_DIR)):
            return {
                "success": False,
                "restored_file": None,
                "backup_path": backup_path,
                "error": f"Original file must be in tests/api/ directory: {original_file}"
            }
        
        # Restore from backup
        backup_content = backup.read_text(encoding="utf-8")
        original.write_text(backup_content, encoding="utf-8")
        
        return {
            "success": True,
            "restored_file": str(original),
            "backup_path": backup_path,
            "error": None
        }
    
    except Exception as e:
        return {
            "success": False,
            "restored_file": None,
            "backup_path": backup_path,
            "error": f"Restore failed: {str(e)}"
        }


def restore_latest_backup(test_file_name: str) -> Dict[str, Any]:
    """
    Restore the latest backup for a specific test file.
    
    Args:
        test_file_name: Test file name without extension (e.g., "test_users")
    
    Returns:
        Restore result dict
    """
    backups = list_backups(test_file_name)
    if not backups:
        return {
            "success": False,
            "restored_file": None,
            "backup_path": None,
            "error": f"No backups found for {test_file_name}"
        }
    
    # Get latest backup (first in sorted list)
    latest = backups[0]
    return restore_from_backup(latest["backup_path"], latest["original_file"])


def restore_all_test_files() -> Dict[str, Dict[str, Any]]:
    """
    Restore all test files from their latest backups.
    
    Returns:
        Dict mapping test_file_name -> restore result
    """
    results = {}
    backups = list_backups()
    
    # Group by test file name
    test_files = {}
    for backup in backups:
        test_file = backup["test_file"]
        if test_file not in test_files:
            test_files[test_file] = []
        test_files[test_file].append(backup)
    
    # Restore latest backup for each test file
    for test_file, file_backups in test_files.items():
        # Latest is first (sorted by timestamp desc)
        latest = file_backups[0]
        test_name = test_file.replace(".py", "")
        results[test_file] = restore_from_backup(
            latest["backup_path"],
            latest["original_file"]
        )
    
    return results


def print_backup_status():
    """Print a summary of all available backups."""
    backups = list_backups()
    
    if not backups:
        print("No backups found in failures/.backups/")
        return
    
    print(f"\nFound {len(backups)} backup(s):\n")
    print(f"{'Test File':<30} {'Timestamp':<20} {'Backup Path'}")
    print("-" * 100)
    
    # Group by test file
    by_test_file = {}
    for backup in backups:
        test_file = backup["test_file"]
        if test_file not in by_test_file:
            by_test_file[test_file] = []
        by_test_file[test_file].append(backup)
    
    for test_file, file_backups in sorted(by_test_file.items()):
        for i, backup in enumerate(file_backups):
            marker = "← LATEST" if i == 0 else ""
            print(f"{test_file:<30} {backup['timestamp']:<20} {backup['backup_name']} {marker}")


if __name__ == "__main__":
    """CLI interface for restore utilities."""
    import sys
    
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == "list":
            print_backup_status()
        
        elif command == "restore":
            if len(sys.argv) < 3:
                print("Usage: python restore_utils.py restore <test_file_name>")
                print("Example: python restore_utils.py restore test_users")
                sys.exit(1)
            
            test_name = sys.argv[2]
            result = restore_latest_backup(test_name)
            if result["success"]:
                print(f"✓ Restored {result['restored_file']} from backup")
            else:
                print(f"✗ Failed: {result['error']}")
        
        elif command == "restore-all":
            results = restore_all_test_files()
            success_count = sum(1 for r in results.values() if r["success"])
            print(f"\nRestored {success_count}/{len(results)} test file(s):\n")
            for test_file, result in results.items():
                status = "✓" if result["success"] else "✗"
                print(f"{status} {test_file}")
                if not result["success"]:
                    print(f"  Error: {result['error']}")
        
        else:
            print("Commands: list, restore <test_name>, restore-all")
    else:
        print("Restore Utilities for Test Files")
        print("\nUsage:")
        print("  python restore_utils.py list              # List all backups")
        print("  python restore_utils.py restore test_users # Restore latest backup for test_users.py")
        print("  python restore_utils.py restore-all        # Restore all test files from latest backups")
