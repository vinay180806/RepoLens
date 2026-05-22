from datetime import datetime
import json
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.columns import Columns
from rich.progress import BarColumn, Progress

# Initialize global rich Console
console = Console()

class RepoMetrics:
    """Computes useful engineering insights from raw GitHub API data."""

    def __init__(self, repo_data, languages, contributors, commits):
        self.repo_data = repo_data
        self.languages = languages
        self.contributors = contributors
        self.commits = commits
        self.owner = repo_data.get("owner", {}).get("login", "Unknown")
        self.name = repo_data.get("name", "Unknown")
        self.full_name = repo_data.get("full_name", f"{self.owner}/{self.name}")
        self.stars = repo_data.get("stargazers_count", 0)
        self.forks = repo_data.get("forks_count", 0)
        self.open_issues = repo_data.get("open_issues_count", 0)
        self.size_kb = repo_data.get("size", 0)
        self.license = (repo_data.get("license") or {}).get("name", "No License")
        self.description = repo_data.get("description") or "No description provided."
        
        # Last commit parsing
        self.last_commit_date = self._parse_last_commit_date()
        self.days_since_last_commit = self._calculate_days_since_last_commit()
        
        # Calculate stats
        self.activity_score = self._calculate_activity_score()
        self.health_status = self._calculate_health_status()
        self.language_percentages = self._calculate_language_percentages()
        self.contributor_stats = self._calculate_contributor_stats()

    def _parse_last_commit_date(self):
        """Extracts the date of the absolute last commit, falling back to pushed_at."""
        if self.commits and len(self.commits) > 0:
            commit_date_str = self.commits[0].get("commit", {}).get("committer", {}).get("date")
            if commit_date_str:
                return datetime.strptime(commit_date_str, "%Y-%m-%dT%H:%M:%SZ")
        
        # Fallback to pushed_at
        pushed_at = self.repo_data.get("pushed_at")
        if pushed_at:
            return datetime.strptime(pushed_at, "%Y-%m-%dT%H:%M:%SZ")
        return None

    def _calculate_days_since_last_commit(self):
        if not self.last_commit_date:
            return 9999
        delta = datetime.utcnow() - self.last_commit_date
        return max(0, delta.days)

    def _calculate_health_status(self):
        """Determines if the repo is active, maintenance, or stale."""
        if self.days_since_last_commit <= 90:
            return "Active"
        elif self.days_since_last_commit <= 180:
            return "Maintenance"
        else:
            return "Stale"

    def _calculate_activity_score(self):
        """
        Computes a 0-100 activity score.
        - Recency of last commit (40 pts)
        - Commit frequency in last 30 commits (30 pts)
        - Open issues health ratio (30 pts)
        """
        score = 0
        
        # 1. Recency of last commit (40 points max)
        if self.days_since_last_commit <= 3:
            score += 40
        elif self.days_since_last_commit <= 14:
            score += 35
        elif self.days_since_last_commit <= 30:
            score += 30
        elif self.days_since_last_commit <= 90:
            score += 20
        elif self.days_since_last_commit <= 180:
            score += 10
            
        # 2. Commit frequency in last 30 days (30 points max)
        # We look at the date of the 30th commit (or last available)
        if self.commits:
            recent_commits_count = 0
            now = datetime.utcnow()
            for c in self.commits:
                date_str = c.get("commit", {}).get("committer", {}).get("date")
                if date_str:
                    c_date = datetime.strptime(date_str, "%Y-%m-%dT%H:%M:%SZ")
                    if (now - c_date).days <= 30:
                        recent_commits_count += 1
            
            if recent_commits_count >= 20:
                score += 30
            elif recent_commits_count >= 10:
                score += 25
            elif recent_commits_count >= 5:
                score += 15
            elif recent_commits_count >= 1:
                score += 5
        
        # 3. Open Issues vs Stars ratio (30 points max)
        # Avoid penalizing active popular repos by using a ratio: stars / (issues + 1)
        # High ratio means many stars relative to open issues (good issue handling or extremely well-loved code)
        ratio = self.stars / (self.open_issues + 1)
        if ratio >= 20 or self.open_issues == 0:
            score += 30
        elif ratio >= 10:
            score += 25
        elif ratio >= 5:
            score += 15
        elif ratio >= 1:
            score += 10
        else:
            score += 5
            
        return score

    def _calculate_language_percentages(self):
        """Computes percentage representation of languages, grouping minor ones into 'Other'."""
        total_bytes = sum(self.languages.values())
        if total_bytes == 0:
            return {}

        sorted_langs = sorted(self.languages.items(), key=lambda x: x[1], reverse=True)
        percentages = {}
        accumulated_percent = 0.0

        for lang, byte_count in sorted_langs:
            percent = (byte_count / total_bytes) * 100
            if percent >= 1.0 or len(percentages) < 4:
                percentages[lang] = round(percent, 1)
                accumulated_percent += percent
            else:
                break

        if accumulated_percent < 99.9:
            other_percent = round(100.0 - accumulated_percent, 1)
            if other_percent > 0:
                percentages["Other"] = other_percent

        return percentages

    def _calculate_contributor_stats(self):
        """
        Computes contributor contributions and Gini-like concentration.
        - High concentration (>60%) = high bus factor risk.
        """
        if not self.contributors:
            return {"top_contributors": [], "concentration": 0.0, "risk": "Unknown"}

        total_top_commits = sum(c.get("contributions", 0) for c in self.contributors)
        if total_top_commits == 0:
            return {"top_contributors": [], "concentration": 0.0, "risk": "Unknown"}

        # Prepare top 5 contributors list
        top_list = []
        for c in self.contributors[:5]:
            contribs = c.get("contributions", 0)
            percent = (contribs / total_top_commits) * 100
            top_list.append({
                "login": c.get("login", "Unknown"),
                "commits": contribs,
                "percentage": round(percent, 1)
            })

        # Calculate concentration of top contributor among the top contributors
        top_commits = self.contributors[0].get("contributions", 0)
        concentration = (top_commits / total_top_commits) * 100

        if concentration > 60:
            risk = "High (Single point of failure)"
        elif concentration > 35:
            risk = "Medium (Moderate division of labor)"
        else:
            risk = "Low (Highly collaborative)"

        return {
            "top_contributors": top_list,
            "concentration": round(concentration, 1),
            "risk": risk
        }

    def to_dict(self):
        """Converts stats to dict for JSON export."""
        return {
            "repository": self.full_name,
            "owner": self.owner,
            "name": self.name,
            "description": self.description,
            "stars": self.stars,
            "forks": self.forks,
            "open_issues": self.open_issues,
            "size_kb": self.size_kb,
            "license": self.license,
            "last_commit_date": self.last_commit_date.strftime("%Y-%m-%d %H:%M:%S UTC") if self.last_commit_date else None,
            "days_since_last_commit": self.days_since_last_commit,
            "health": {
                "status": self.health_status,
                "activity_score": self.activity_score
            },
            "languages": self.language_percentages,
            "contributors": {
                "concentration_percent": self.contributor_stats["concentration"],
                "bus_factor_risk": self.contributor_stats["risk"],
                "top": self.contributor_stats["top_contributors"]
            }
        }


class TerminalFormatter:
    """Utility class to print beautiful CLI layouts using the Rich library."""

    @staticmethod
    def print_banner(metrics: RepoMetrics):
        """Prints a gorgeous panel summarizing the repository details."""
        health_colors = {"Active": "bold green", "Maintenance": "bold yellow", "Stale": "bold red"}
        health_col = health_colors.get(metrics.health_status, "bold white")

        banner_text = Text()
        banner_text.append(f"\n📁 {metrics.full_name}\n", style="bold cyan")
        banner_text.append(f"📄 {metrics.description}\n\n", style="italic white")
        banner_text.append("⚖️  License: ", style="bold dim")
        banner_text.append(f"{metrics.license}   ", style="dim")
        banner_text.append("💾 Size: ", style="bold dim")
        
        size_str = f"{metrics.size_kb / 1024:.1f} MB" if metrics.size_kb > 1000 else f"{metrics.size_kb} KB"
        banner_text.append(f"{size_str}   ", style="dim")
        banner_text.append("Health: ", style="bold dim")
        banner_text.append(f"{metrics.health_status}", style=health_col)

        console.print(Panel(banner_text, border_style="cyan", subtitle="GitHub Repository Insights"))

    @staticmethod
    def print_statistics(metrics: RepoMetrics):
        """Prints general stats and calculated insights side-by-side."""
        
        # General stats table
        stats_table = Table(title="📊 Key Statistics", show_header=False, expand=True, box=None)
        stats_table.add_column("Metric", style="bold magenta", width=20)
        stats_table.add_column("Value", style="bold white")
        
        stats_table.add_row("⭐ Stars", f"{metrics.stars:,}")
        stats_table.add_row("🍴 Forks", f"{metrics.forks:,}")
        stats_table.add_row("🐛 Open Issues", f"{metrics.open_issues:,}")
        
        # Insights table
        insights_table = Table(title="💡 Computed Health & Activity", show_header=False, expand=True, box=None)
        insights_table.add_column("Insight", style="bold gold1", width=25)
        insights_table.add_column("Value", style="bold white")
        
        # Color activity score based on rating
        act_col = "green" if metrics.activity_score >= 75 else "yellow" if metrics.activity_score >= 40 else "red"
        insights_table.add_row("Activity Score", f"[{act_col}]{metrics.activity_score}/100[/]")
        
        # Last commit display
        commit_date_str = metrics.last_commit_date.strftime("%Y-%m-%d") if metrics.last_commit_date else "Never"
        days_str = "today" if metrics.days_since_last_commit == 0 else f"{metrics.days_since_last_commit} days ago"
        insights_table.add_row("Last Commit Date", f"{commit_date_str} ([cyan]{days_str}[/])")
        
        # Contributor concentration
        con_col = "red" if metrics.contributor_stats["concentration"] > 60 else "yellow" if metrics.contributor_stats["concentration"] > 35 else "green"
        insights_table.add_row(
            "Contributor Risk",
            f"[{con_col}]{metrics.contributor_stats['risk']}[/] ([dim]{metrics.contributor_stats['concentration']}% top share[/])"
        )
        
        # Print side-by-side using panels
        col1 = Panel(stats_table, border_style="magenta")
        col2 = Panel(insights_table, border_style="gold1")
        
        console.print(Columns([col1, col2], expand=True))

    @staticmethod
    def print_languages(metrics: RepoMetrics):
        """Renders the language breakdown bar and legend."""
        if not metrics.language_percentages:
            console.print("[dim]No language breakdown available.[/dim]\n")
            return
            
        console.print("\n[bold cyan]🎨 Primary Languages[/bold cyan]")
        
        # Color palette for languages
        colors = ["bold green1", "bold bright_magenta", "bold yellow", "bold sky_blue", "bold red", "bold bright_blue"]
        
        bar_text = Text()
        legend_items = []
        
        for idx, (lang, percent) in enumerate(metrics.language_percentages.items()):
            col = colors[idx % len(colors)]
            blocks = int(round(percent / 2)) # 50 characters max width
            if blocks == 0 and percent > 0:
                blocks = 1
            bar_text.append("█" * blocks, style=col)
            legend_items.append(f"[{col}]█[/] {lang}: {percent}%")
            
        # Output progress bar
        console.print(Panel(bar_text, expand=False, padding=(0, 2), border_style="dim"))
        
        # Output legend in nice columns
        console.print("   " + "   ".join(legend_items))
        console.print()

    @staticmethod
    def print_contributors(metrics: RepoMetrics):
        """Displays top contributors in an elegant list/table."""
        top_contribs = metrics.contributor_stats["top_contributors"]
        if not top_contribs:
            console.print("[dim]No contributor information available.[/dim]\n")
            return
            
        table = Table(title="👑 Top Contributors", box=None, header_style="bold steel_blue1", show_lines=False)
        table.add_column("Rank", style="dim", justify="right", width=5)
        table.add_column("Username", style="bold white", width=25)
        table.add_column("Contributions", style="cyan", justify="right", width=15)
        table.add_column("Percentage", style="green", justify="right", width=12)
        
        for idx, tc in enumerate(top_contribs):
            table.add_row(
                str(idx + 1),
                tc["login"],
                f"{tc['commits']:,}",
                f"{tc['percentage']}%"
            )
            
        console.print(table)
        console.print()

    @staticmethod
    def print_comparison(metrics1: RepoMetrics, metrics2: RepoMetrics):
        """Compares two repositories side-by-side in a comparative table."""
        table = Table(title=f"⚔️ Repository Duel: {metrics1.full_name} vs {metrics2.full_name}", box=None, header_style="bold sky_blue1")
        
        table.add_column("Feature / Metric", style="bold cyan", width=25)
        table.add_column(metrics1.full_name, justify="center", width=35)
        table.add_column(metrics2.full_name, justify="center", width=35)
        
        # 1. Description
        table.add_row("Description", f"[italic]{metrics1.description[:60]}...[/]", f"[italic]{metrics2.description[:60]}...[/]")
        table.add_row("", "", "") # spacing
        
        # Function to compare numeric values and highlight the larger/better one
        def get_winner_styled(val1, val2, higher_is_better=True, formatter=lambda x: str(x)):
            if val1 == val2:
                return formatter(val1), formatter(val2)
            
            is1_winner = (val1 > val2) if higher_is_better else (val1 < val2)
            if is1_winner:
                return f"[bold green]{formatter(val1)} 🏆[/]", f"[dim]{formatter(val2)}[/]"
            else:
                return f"[dim]{formatter(val1)}[/]", f"[bold green]{formatter(val2)} 🏆[/]"

        # Stats comparisons
        stars1, stars2 = get_winner_styled(metrics1.stars, metrics2.stars, formatter=lambda x: f"{x:,}")
        forks1, forks2 = get_winner_styled(metrics1.forks, metrics2.forks, formatter=lambda x: f"{x:,}")
        
        # Less open issues relative to stars is better, but raw open issues: smaller is better.
        # Let's compare raw open issues, smaller is better.
        issues1, issues2 = get_winner_styled(metrics1.open_issues, metrics2.open_issues, higher_is_better=False, formatter=lambda x: f"{x:,}")
        
        # Activity Score
        score1, score2 = get_winner_styled(metrics1.activity_score, metrics2.activity_score)
        
        # Last Commit (smaller days since commit is better)
        recency_formatter = lambda d: f"{d} days ago" if d != 9999 else "Never"
        days1, days2 = get_winner_styled(metrics1.days_since_last_commit, metrics2.days_since_last_commit, higher_is_better=False, formatter=recency_formatter)
        
        # Size (smaller is better or just size display)
        sz1_str = f"{metrics1.size_kb / 1024:.1f} MB" if metrics1.size_kb > 1024 else f"{metrics1.size_kb} KB"
        sz2_str = f"{metrics2.size_kb / 1024:.1f} MB" if metrics2.size_kb > 1024 else f"{metrics2.size_kb} KB"
        
        # Languages
        lang1 = ", ".join(list(metrics1.language_percentages.keys())[:2])
        lang2 = ", ".join(list(metrics2.language_percentages.keys())[:2])

        # Add comparison rows
        table.add_row("⭐ Stars", stars1, stars2)
        table.add_row("🍴 Forks", forks1, forks2)
        table.add_row("🐛 Open Issues", issues1, issues2)
        table.add_row("🔥 Activity Score", score1, score2)
        table.add_row("🕒 Last Commit Recency", days1, days2)
        table.add_row("💾 Repository Size", sz1_str, sz2_str)
        table.add_row("⚖️ License", metrics1.license, metrics2.license)
        table.add_row("🎨 Top Languages", lang1, lang2)
        
        console.print(Panel(table, border_style="sky_blue1"))

    @staticmethod
    def print_error(message: str, title: str = "Error"):
        """Displays error messages in a consistent premium banner style."""
        error_text = Text()
        error_text.append(f"❌ {message}\n\n", style="bold white")
        error_text.append("Suggestions:\n", style="bold dim")
        error_text.append("• Double-check spelling of owner/repo (e.g. microsoft/vscode).\n", style="dim")
        error_text.append("• Ensure you have an active internet connection.\n", style="dim")
        error_text.append("• If you suspect rate limits, set the GITHUB_TOKEN environment variable.", style="dim")
        
        console.print(Panel(error_text, title=f"[bold red]{title}[/bold red]", border_style="red"))
