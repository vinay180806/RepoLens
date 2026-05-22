# GitHub Repo Analyzer

A premium, highly resilient, and fast Command Line Interface (CLI) tool written in Python that fetches, processes, and analyzes GitHub repository statistics. It calculates custom health and activity metrics, analyzes contributor distribution (bus factor risk), visualizes programming language breakdowns, and supports side-by-side comparison of multiple repositories.

## Features

- **Metadata Analysis:** Fetch stars, forks, open issues, repository size, license, and description.
- **Custom Health & Activity Insights:**
  - **Activity Score (0-100):** A custom weighted algorithm based on commit recency, commit velocity, and issue-to-star ratios.
  - **Health Status:** Evaluates whether a repository is **Active**, under **Maintenance**, or **Stale** based on the latest commit date.
- **Visual Language Breakdown:** Analyzes programming language usage and renders a beautifully styled horizontal ratio bar directly in your terminal.
- **Contributor Risk Assessment (Bus Factor):** Computes contribution concentration percentage and warns if a repository has a high concentration of commits from a single contributor.
- **Repository Comparisons:** Compare two repositories side-by-side in a beautifully styled duel table, highlighting winners in each category.
- **Structured Data Export:** Export full repository reports to JSON using the `--export` option.
- **Resilient Network Architecture:** Robust error catching with hard 5-second timeouts, retry friendliness, rate limit remaining indicators, and comprehensive user validation.

## Installation

Ensure you have Python 3.8+ installed.

1. Clone the repository or download the source files.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

### Optional: GitHub API Token

The CLI works without a token for normal usage, but GitHub imposes strict unauthenticated rate limits. To avoid rate limiting, set a GitHub Personal Access Token using the `GITHUB_TOKEN` environment variable.

1. Visit https://github.com/settings/tokens
2. Generate a new token. For public repository data, the default permissions are sufficient.
3. Do not commit the token to source control.

On Windows PowerShell:

```powershell
setx GITHUB_TOKEN "your_token_here"
```

On macOS / Linux:

```bash
export GITHUB_TOKEN="your_token_here"
```

Reload your terminal after setting the variable.

## Run

To analyze a single repository:

```bash
python main.py microsoft/vscode
```

To compare two repositories:

```bash
python main.py compare pytorch/pytorch tensorflow/tensorflow
```

To export the analysis output to a JSON file:

```bash
python main.py microsoft/vscode --export report.json
```

## Example Output

### Single Repository Analysis Output
```text
📁 microsoft/vscode
📄 Code editing. Redefined.

⚖️ License: MIT License   💾 Size: 412.3 MB   Health: Active

┌── 📊 Key Statistics ────────────────────────────────┐  ┌── 💡 Computed Health & Activity ────────────────────────┐
│ ⭐ Stars                 165,302                     │  │ Activity Score          95/100                          │
│ 🍴 Forks                 28,495                      │  │ Last Commit Date        2026-05-22 (today)              │
│ 🐛 Open Issues           4,821                       │  │ Contributor Risk        Low (Highly collaborative)      │
│                                                     │  │                         (18.2% top share)               │
└─────────────────────────────────────────────────────┘  └─────────────────────────────────────────────────────────┘

🎨 Primary Languages
██████████████████████████████  TypeScript: 62.4%   JavaScript: 15.2%   CSS: 8.3%   Python: 5.1%   Other: 9.0%

👑 Top Contributors
  Rank   Username                      Contributions     Percentage
────────────────────────────────────────────────────────────────────
     1   aeschli                             25,483          18.2%
     2   dbaeumer                            21,987          15.7%
     3   mjfvz                               19,832          14.2%
     4   joaomoreno                          18,129          12.9%
     5   isidorn                             15,482          11.1%
```

## Error Handling

The application is built to withstand extreme API scenarios and bad user interactions:

1. **API Timeout (Slow Connections):** A strict `5.0s` timeout is set on all API calls. If the API is slow, the tool aborts gracefully and raises:
   ```text
   ❌ The request to GitHub API timed out (5s limit). Please check your internet connection.
   ```
2. **API Errors (404/5xx):**
   - **404 Repo Not Found:** Triggers when a repository is spelled incorrectly or is private:
     ```text
     ❌ The repository was not found. Please verify owner/repo spelling.
     ```
   - **403/429 Rate Limiting:** In case of rate limits, the tool inspects GitHub's rate limit headers to let you know exactly when your quota resets:
     ```text
     ❌ GitHub API rate limit exceeded.
     Rate limit will reset at: 2026-05-22 13:45:00 local time.
     To increase your rate limit, set the GITHUB_TOKEN environment variable.
     ```
3. **Bad User Input:** Rejects malformed arguments (like spaces, double slashes, missing owner, etc.) on the client-side *before* invoking the API, preserving precious rate limit quota:
   ```text
   ❌ Invalid repository format: 'hello'. Expected 'owner/repo'.
   ```

## Tech Stack

- **Core Logic:** Python 3
- **HTTP Client:** `requests`
- **CLI Design & Rendering:** `rich`
- **Standard Libraries:** `argparse`, `re`, `json`, `datetime`
