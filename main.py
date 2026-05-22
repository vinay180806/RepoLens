import sys
import os
import re
import json
import argparse
from datetime import datetime, timezone

# Reconfigure standard streams to UTF-8 on Windows to support emojis and unicode formatting
if sys.platform.startswith("win"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


from github_api import (
    GitHubAPIClient, 
    RepositoryNotFoundError, 
    RateLimitExceededError, 
    APIError, 
    NetworkTimeoutError,
    GitHubAPIError
)
from formatter import RepoMetrics, TerminalFormatter, console

# GitHub repository regex pattern (owner/repo)
# GitHub usernames/orgs can contain alphanumeric chars and hyphens.
# Repo names can contain alphanumeric, hyphens, underscores, and dots.
REPO_PATTERN = re.compile(r"^[a-zA-Z0-9\-]+/[a-zA-Z0-9\-_.]+$")

def validate_repo_input(repo_str: str) -> bool:
    """
    Validates the owner/repo format.
    Rejects: hello, /////, abc///, spaces, or weird symbols.
    """
    if not repo_str:
        return False
    # Strip whitespace to check if the input contains spaces
    if " " in repo_str.strip():
        return False
    return bool(REPO_PATTERN.match(repo_str))

def fetch_repo_metrics(client: GitHubAPIClient, repo_fullname: str) -> RepoMetrics:
    """Helper function to fetch all required data for a single repository."""
    owner, repo = repo_fullname.split("/")
    
    # Run requests under a progress spinner
    with console.status(f"[bold green]Fetching {repo_fullname} data...[/]"):
        repo_data = client.get_repo(owner, repo)
        languages = client.get_languages(owner, repo)
        contributors = client.get_contributors(owner, repo)
        commits = client.get_last_commits(owner, repo)
        
    return RepoMetrics(repo_data, languages, contributors, commits)

def main():
    parser = argparse.ArgumentParser(
        description="GitHub Repository Analyzer CLI - Analyze & Compare repos dynamically.",
        add_help=True
    )
    
    # We want to support:
    # 1. python main.py owner/repo
    # 2. python main.py compare owner1/repo1 owner2/repo2
    # To do this gracefully with standard argparse, we use positional arguments.
    parser.add_argument(
        "args", 
        nargs="+", 
        help="Repository in 'owner/repo' format, OR 'compare owner1/repo1 owner2/repo2'"
    )
    
    parser.add_argument(
        "--export", 
        help="Path to export the analysis output as a JSON file", 
        type=str, 
        default=None
    )
    
    # If no arguments provided
    if len(sys.argv) < 2:
        parser.print_help()
        sys.exit(1)

    parsed_args = parser.parse_args()
    args_list = parsed_args.args
    export_path = parsed_args.export

    # Parse and Validate inputs based on action mode
    is_compare_mode = (args_list[0].lower() == "compare")
    
    # Instantiate API client
    client = GitHubAPIClient()

    if is_compare_mode:
        if len(args_list) < 3:
            console.print("\n[bold red]Error:[/] Compare mode requires two repositories.", style="red")
            console.print("Usage: [bold yellow]python main.py compare owner1/repo1 owner2/repo2[/]\n")
            sys.exit(1)
            
        repo1 = args_list[1]
        repo2 = args_list[2]
        
        # Validate inputs
        if not validate_repo_input(repo1):
            TerminalFormatter.print_error(
                f"Invalid repository format: '{repo1}'.",
                "Bad User Input"
            )
            sys.exit(1)
            
        if not validate_repo_input(repo2):
            TerminalFormatter.print_error(
                f"Invalid repository format: '{repo2}'.",
                "Bad User Input"
            )
            sys.exit(1)

        try:
            metrics1 = fetch_repo_metrics(client, repo1)
            metrics2 = fetch_repo_metrics(client, repo2)
            
            # Print side-by-side comparison
            TerminalFormatter.print_comparison(metrics1, metrics2)
            
            # Handle JSON export if requested
            if export_path:
                export_data = {
                    "mode": "comparison",
                    "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "repo1": metrics1.to_dict(),
                    "repo2": metrics2.to_dict()
                }
                with open(export_path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=4)
                console.print(f"\n[bold green]✓[/bold green] Comparison successfully exported to [cyan]{export_path}[/cyan]\n")

        except RepositoryNotFoundError as e:
            TerminalFormatter.print_error(str(e), "Repository Not Found")
            sys.exit(1)
        except RateLimitExceededError as e:
            msg = str(e)
            if e.reset_datetime:
                msg += f"\nRate limit will reset at: {e.reset_datetime.strftime('%Y-%m-%d %H:%M:%S local time')}."
            msg += "\nTo increase your rate limit, set the GITHUB_TOKEN environment variable."
            TerminalFormatter.print_error(msg, "Rate Limit Exceeded")
            sys.exit(1)
        except NetworkTimeoutError as e:
            TerminalFormatter.print_error(str(e), "Request Timeout")
            sys.exit(1)
        except APIError as e:
            TerminalFormatter.print_error(str(e), "GitHub API Error")
            sys.exit(1)
        except GitHubAPIError as e:
            TerminalFormatter.print_error(str(e), "Communication Error")
            sys.exit(1)
            
    else:
        # Single repository mode
        repo_fullname = args_list[0]
        
        if not validate_repo_input(repo_fullname):
            TerminalFormatter.print_error(
                f"Invalid repository format: '{repo_fullname}'. Expected 'owner/repo'.\n"
                f"Ensure there are no spaces, double slashes, or special symbols.",
                "Bad User Input"
            )
            sys.exit(1)
            
        try:
            metrics = fetch_repo_metrics(client, repo_fullname)
            
            # Print beautiful layouts
            TerminalFormatter.print_banner(metrics)
            TerminalFormatter.print_statistics(metrics)
            TerminalFormatter.print_languages(metrics)
            TerminalFormatter.print_contributors(metrics)
            
            # Handle export if requested
            if export_path:
                export_data = {
                    "mode": "single",
                    "timestamp": datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S UTC"),
                    "data": metrics.to_dict()
                }
                with open(export_path, "w", encoding="utf-8") as f:
                    json.dump(export_data, f, indent=4)
                console.print(f"[bold green]✓[/bold green] Analysis successfully exported to [cyan]{export_path}[/cyan]\n")
                
        except RepositoryNotFoundError as e:
            TerminalFormatter.print_error(str(e), "Repository Not Found")
            sys.exit(1)
        except RateLimitExceededError as e:
            msg = str(e)
            if e.reset_datetime:
                msg += f"\nRate limit will reset at: {e.reset_datetime.strftime('%Y-%m-%d %H:%M:%S local time')}."
            msg += "\nTo increase your rate limit, set the GITHUB_TOKEN environment variable."
            TerminalFormatter.print_error(msg, "Rate Limit Exceeded")
            sys.exit(1)
        except NetworkTimeoutError as e:
            TerminalFormatter.print_error(str(e), "Request Timeout")
            sys.exit(1)
        except APIError as e:
            TerminalFormatter.print_error(str(e), "GitHub API Error")
            sys.exit(1)
        except GitHubAPIError as e:
            TerminalFormatter.print_error(str(e), "Communication Error")
            sys.exit(1)

if __name__ == "__main__":
    main()
