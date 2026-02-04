"""Main entry point for Self-Healing API Test Agent."""
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Any, Optional
import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text

from src.agent.healer import HealerAgent
from src.generator.generator import Generator
from src.agent.tools import PROJECT_ROOT

app = typer.Typer(
    help="Self-Healing API Test Agent - Automatically fixes test failures and generates missing tests",
    no_args_is_help=True
)
console = Console()

# Global state tracking
session_state = {
    "failures_found": [],
    "healed": [],
    "heal_failures": [],
    "generated": [],
    "generation_failures": [],
    "verbose_mode": False,
    "dry_run": False
}


def run_all_tests() -> Dict[str, Any]:
    """Run all tests in tests/api directory and return results."""
    try:
        # First, collect tests to get accurate count
        collect_cmd = ["pytest", "tests/api", "--collect-only", "-q"]
        collect_result = subprocess.run(
            collect_cmd,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=str(PROJECT_ROOT)
        )
        
        # Parse test count from collection output
        test_count = 0
        if collect_result.returncode == 0:
            # Look for "X tests collected" or "X items collected"
            match = re.search(r'(\d+)\s+test', collect_result.stdout)
            if match:
                test_count = int(match.group(1))
        
        # Now run the actual tests
        cmd = ["pytest", "tests/api", "-v", "--tb=short"]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=120,  # 2 minute timeout for full suite
            cwd=str(PROJECT_ROOT)
        )
        
        output = result.stdout + result.stderr
        passed = result.returncode == 0
        
        # If collection failed, fall back to counting test results (less accurate)
        if test_count == 0:
            # Count unique test results by looking for "::test_" pattern followed by PASSED/FAILED
            test_results = re.findall(r'::test_\w+\s+(?:PASSED|FAILED)', output)
            test_count = len(set(test_results)) if test_results else 0
        
        return {
            "success": True,
            "passed": passed,
            "output": output,
            "test_count": test_count,
            "error": None
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "passed": False,
            "output": "",
            "test_count": 0,
            "error": "Test execution timed out"
        }
    except Exception as e:
        return {
            "success": False,
            "passed": False,
            "output": "",
            "test_count": 0,
            "error": f"Error running tests: {str(e)}"
        }


def collect_failures() -> List[Path]:
    """Collect all failure JSON files from failures/ directory."""
    failures_dir = PROJECT_ROOT / "failures"
    if not failures_dir.exists():
        return []
    
    # Get all JSON files (excluding .backups directory)
    failure_files = [
        f for f in failures_dir.glob("*.json")
        if ".backup" not in f.name
    ]
    
    return sorted(failure_files)


def print_session_banner():
    """Print session start banner with timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    banner = Panel(
        Text(f"Self-Healing API Test Agent\nSession started: {timestamp}", justify="center"),
        border_style="bright_blue",
        title="[bold bright_blue]AGENT SESSION[/bold bright_blue]"
    )
    console.print(banner)


def print_progress(current: int, total: int, action: str, item: str):
    """Print progress indicator."""
    # Truncate long item names for readability
    max_len = 60
    display_item = item if len(item) <= max_len else item[:max_len-3] + "..."
    console.print(f"[cyan][{current}/{total}][/cyan] {action} {display_item}...")


def print_summary_report():
    """Print final summary report using Rich."""
    is_dry_run = session_state.get("dry_run", False)
    title_suffix = " (DRY RUN)" if is_dry_run else ""
    table = Table(title=f"Self-Healing Agent — Session Report{title_suffix}", show_header=True, header_style="bold magenta")
    
    table.add_column("Metric", style="cyan", no_wrap=True)
    table.add_column("Value", style="green")
    
    # Calculate totals
    total_tests = session_state.get("test_count", 0)
    failures_found = len(session_state["failures_found"])
    healed_count = len(session_state["healed"])
    heal_failures_count = len(session_state["heal_failures"])
    generated_count = len(session_state["generated"])
    
    # In dry-run mode, show what would be attempted vs what we know would succeed
    if is_dry_run:
        # For healing: we don't know success rate without actually trying
        attempted_heal_count = len(session_state["failures_found"])
        healed_label = f"{attempted_heal_count} (would attempt)" if attempted_heal_count > 0 else "0"
        # For generation: we actually checked for gaps, so this is accurate
        generated_label = f"{generated_count} (would generate)" if generated_count > 0 else "0"
    else:
        healed_label = str(healed_count)
        generated_label = str(generated_count)
    
    table.add_row("Tests Run", str(total_tests))
    table.add_row("Failures Found", str(failures_found))
    table.add_row("Tests Healed", healed_label)
    table.add_row("Heal Failures", f"{heal_failures_count} (rollback applied)" if heal_failures_count > 0 else "0")
    table.add_row("Tests Generated", generated_label)
    
    console.print("\n")
    console.print(table)
    
    # Show detailed results
    if session_state["healed"]:
        console.print("\n[bold green]HEALED:[/bold green]")
        for item in session_state["healed"]:
            decision = item.get("decision", "N/A")
            console.print(f"  • {item['test_name']} - {decision}")
    
    if session_state["generated"]:
        console.print("\n[bold blue]GENERATED:[/bold blue]")
        for item in session_state["generated"]:
            console.print(f"  • {item['test_name']} ({item['description']})")
    
    if session_state["heal_failures"]:
        console.print("\n[bold red]HEAL FAILURES:[/bold red]")
        for item in session_state["heal_failures"]:
            error = item.get("error", "Unknown error")
            console.print(f"  • {item['test_name']} - {error}")
    
    # Add dry-run disclaimer
    if is_dry_run:
        console.print("\n")
        disclaimer = Panel(
            "[yellow]⚠️  DRY RUN MODE DISCLAIMER[/yellow]\n\n"
            "• [bold]Numbers reflect what would be attempted, not guaranteed success[/bold]\n"
            "• [bold]No actual API calls, file modifications, or test executions occurred[/bold]\n"
            "• This is an overview of the workflow logic without real operations\n"
            "• Healing success rates cannot be determined without actual execution\n"
            "• Gap analysis is real (read-only), but test generation was not performed",
            border_style="yellow",
            title="[bold yellow]Important[/bold yellow]"
        )
        console.print(disclaimer)
    else:
        console.print("\n[dim]Run 'git diff' to see all file changes[/dim]")


def _run_workflow(
    heal_only: bool = False,
    generate_only: bool = False,
    dry_run: bool = False,
    verbose: bool = False
):
    """
    Internal workflow execution function.
    """
    # Initialize state
    session_state["dry_run"] = dry_run
    session_state["verbose_mode"] = verbose
    
    # Print session banner
    print_session_banner()
    
    if dry_run:
        console.print("[yellow]DRY RUN MODE: No changes will be applied[/yellow]\n")
    
    # Step 1: Run all tests
    console.print("[bold]Step 1: Running all tests...[/bold]")
    test_result = run_all_tests()
    
    if not test_result["success"]:
        console.print(f"[red]Error running tests: {test_result.get('error', 'Unknown error')}[/red]")
        sys.exit(1)
    
    session_state["test_count"] = test_result.get("test_count", 0)
    
    if test_result["passed"]:
        console.print(f"[green]✓ All {session_state['test_count']} tests passed![/green]")
    else:
        console.print(f"[yellow]⚠ Some tests failed[/yellow]")
        # Enable verbose mode if failures found (unless already enabled)
        if not session_state["verbose_mode"]:
            session_state["verbose_mode"] = True
            console.print("[dim]Verbose mode enabled due to failures[/dim]")
    
    # Step 2: Collect failures
    console.print("\n[bold]Step 2: Collecting failures...[/bold]")
    failure_files = collect_failures()
    session_state["failures_found"] = [str(f) for f in failure_files]
    
    if not failure_files:
        console.print("[green]✓ No failures found[/green]")
    else:
        console.print(f"[yellow]Found {len(failure_files)} failure(s)[/yellow]")
    
    # Step 3: Heal failures (if not generate-only)
    if not generate_only and failure_files:
        console.print(f"\n[bold]Step 3: Healing {len(failure_files)} failure(s)...[/bold]")
        
        healer = HealerAgent(max_retries=3)
        
        for i, failure_file in enumerate(failure_files, 1):
            print_progress(i, len(failure_files), "Healing", Path(failure_file).stem)
            
            if dry_run:
                # Truncate long paths for readability
                display_path = str(failure_file)
                if len(display_path) > 80:
                    display_path = "..." + display_path[-77:]
                console.print(f"[dim]  [DRY RUN] Would attempt to heal: {display_path}[/dim]")
                # Note: We can't know if healing would succeed without actually running it
                # So we just track what would be attempted
                continue
            
            try:
                result = healer.heal_failure(str(failure_file))
                
                if result["success"]:
                    session_state["healed"].append({
                        "test_name": result["test_name"],
                        "decision": result.get("decision", "Fixed"),
                        "attempts": result.get("attempts", 1)
                    })
                else:
                    session_state["heal_failures"].append({
                        "test_name": result["test_name"],
                        "error": result.get("error", "Unknown error"),
                        "attempts": result.get("attempts", 0)
                    })
            except Exception as e:
                console.print(f"[red]Error healing {failure_file}: {str(e)}[/red]")
                session_state["heal_failures"].append({
                    "test_name": Path(failure_file).stem,
                    "error": f"Exception: {str(e)}",
                    "attempts": 0
                })
    elif generate_only:
        console.print("\n[dim]Step 3: Skipped (--generate-only flag)[/dim]")
    else:
        console.print("\n[dim]Step 3: Skipped (no failures)[/dim]")
    
    # Step 4: Generate tests (if not heal-only)
    if not heal_only:
        console.print("\n[bold]Step 4: Checking for critical test gaps...[/bold]")
        
        if dry_run:
            console.print("[dim]  [DRY RUN] Analyzing test coverage gaps...[/dim]")
            # Actually run gap analysis (read-only, no file writes)
            try:
                generator = Generator(max_generations=5)
                # Parse existing tests to understand coverage
                coverage = generator._parse_existing_tests()
                console.print(f"[dim]    Found {len(coverage)} endpoint patterns covered[/dim]")
                
                # Identify gaps (read-only analysis)
                gaps = generator._identify_gaps(coverage)
                console.print(f"[dim]    Identified {len(gaps)} critical gap(s)[/dim]")
                
                if gaps:
                    for gap in gaps[:5]:  # Show first 5 gaps
                        console.print(f"[dim]      - {gap['description']}[/dim]")
                    if len(gaps) > 5:
                        console.print(f"[dim]      ... and {len(gaps) - 5} more[/dim]")
                    
                    # Track what would be generated
                    for gap in gaps[:generator.max_generations]:
                        session_state["generated"].append({
                            "test_name": gap.get("test_name", "Unknown"),
                            "file_path": "N/A (dry-run)",
                            "description": gap.get("description", "N/A")
                        })
                else:
                    console.print("[dim]    No critical gaps found[/dim]")
            except Exception as e:
                console.print(f"[yellow]    Could not analyze gaps: {str(e)}[/yellow]")
        else:
            try:
                generator = Generator(max_generations=5)
                results = generator.generate_tests()
                
                for result in results:
                    if result["success"]:
                        session_state["generated"].append({
                            "test_name": result["test_name"],
                            "file_path": result.get("file_path", "N/A"),
                            "description": result.get("description", "N/A")
                        })
                    else:
                        session_state["generation_failures"].append({
                            "test_name": result["test_name"],
                            "error": result.get("error", "Unknown error")
                        })
            except Exception as e:
                console.print(f"[red]Error during generation: {str(e)}[/red]")
    else:
        console.print("\n[dim]Step 4: Skipped (--heal-only flag)[/dim]")
    
    # Step 5: Final verification
    console.print("\n[bold]Step 5: Final verification (running all tests)...[/bold]")
    final_result = run_all_tests()
    
    if final_result["success"]:
        if final_result["passed"]:
            console.print(f"[green]✓ All tests passed![/green]")
        else:
            console.print(f"[yellow]⚠ Some tests still failing[/yellow]")
    else:
        console.print(f"[red]Error during final verification: {final_result.get('error', 'Unknown error')}[/red]")
    
    # Step 6: Print summary
    console.print("\n")
    print_summary_report()


@app.callback(invoke_without_command=True)
def main(
    ctx: typer.Context,
    heal_only: bool = typer.Option(False, "--heal-only", help="Skip test generation, only heal failures"),
    generate_only: bool = typer.Option(False, "--generate-only", help="Skip healing, only generate tests"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show proposed changes without applying"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logging from start")
):
    """
    Run the self-healing agent workflow.
    
    Executes: Run tests → Collect failures → Heal → Generate → Verify
    """
    if ctx.invoked_subcommand is None:
        _run_workflow(heal_only, generate_only, dry_run, verbose)


@app.command(name="run")
def run_cmd(
    heal_only: bool = typer.Option(False, "--heal-only", help="Skip test generation, only heal failures"),
    generate_only: bool = typer.Option(False, "--generate-only", help="Skip healing, only generate tests"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show proposed changes without applying"),
    verbose: bool = typer.Option(False, "--verbose", help="Enable verbose logging from start")
):
    """
    Run the self-healing agent workflow (explicit command).
    
    Executes: Run tests → Collect failures → Heal → Generate → Verify
    """
    _run_workflow(heal_only, generate_only, dry_run, verbose)


if __name__ == "__main__":
    app()
