# Engineering Decisions and Answers

This document outlines the architectural decisions, metrics philosophy, error resilience design, and scalability considerations for the **GitHub Repository Analyzer CLI**.

---

## 1. Technical Stack Selection

### Why Python, Requests, and Rich?
- **Python for API and Data-Heavy CLIs:** Python is the premier language for scripting, data aggregation, and API consumption. Unlike Node.js, which brings along a massive and heavy `node_modules` dependency tree, Python's ecosystem is clean and lightweight.
- **Why `requests` instead of `urllib` or async frameworks like `httpx`?**
  - For a standard interactive CLI that queries 1-2 repositories sequentially, the synchronous simplicity of `requests` is unmatched. It allows fast iteration, readable error blocks, and clean exception handling.
  - Adding asynchronous loops (`aiohttp` or `httpx`) for single-repository fetches introduces unnecessary complexity without any tangible latency benefits (the bottleneck is GitHub's network latency, not Python's thread execution).
  - For the **Compare** feature, fetching the two repos sequentially takes around `0.8 - 1.5s`, which is well within acceptable human interface constraints.
- **Why `rich`?**
  - Terminal presentation is a key aspect of user experience. Raw JSON dumps or unstyled text fail to convey structure.
  - `rich` provides production-grade progress spinners, columns, panels, tables, and colors with zero-config terminal detection. It turns a standard CLI wrapper into a premium interactive dashboard.

---

## 2. Metrics & Insights Philosophy

A simple API wrapper that displays raw stars and forks is trivial. To build a *useful* tool, we designed custom computed metrics:

### A. Activity Score (0-100)
Stars and forks only reflect historical popularity—not the current state of development. To measure actual *velocity*, we calculated a weighted activity score combining three facets:
1. **Commit Recency (40% weight):** Measured by the number of days since the last push/commit on the default branch. A commit within 3 days earns full points (40), decaying linearly to 0 points after 6 months.
2. **Commit Velocity (30% weight):** Counts how many of the top 30 commits occurred in the last 30 days. This measures ongoing momentum.
3. **Open Issues Ratio (30% weight):** Calculated as `stars / (open_issues + 1)`. Rather than penalizing popular repositories with high issue counts, we evaluate issue volume relative to popularity. A healthy ratio guarantees maximum points.

### B. Health Status (Active, Maintenance, Stale)
- **Active:** Has a push/commit within 90 days.
- **Maintenance:** Last commit is between 90 and 180 days. The codebase is stable, but not abandoned.
- **Stale:** No commits for >180 days. The project is potentially abandoned or unmaintained.

### C. Contributor Risk (Bus Factor Analysis)
Calculates Gini-like contribution concentration:
$$\text{Concentration} = \frac{\text{Commits of top contributor}}{\text{Total commits of top 30 contributors}} \times 100$$
- If a single author accounts for **>60%** of the project's top activity, we flag the repository as **High Risk (Single point of failure / Low Bus Factor)**.
- Highly distributed projects maintain a concentration **<35%**, indicating healthy collaborative structures.

---

## 3. Resilience and Error Handling Strategy

GitHub API testing will actively look for vulnerabilities in client robustness. We addressed the three core failure domains:

1. **Slow API / Connection Issues:**
   - Defaulted all network requests to a strict `timeout=5.0`.
   - Any network freeze is caught via `requests.Timeout` and re-raised as a structured `NetworkTimeoutError` showing a highly readable warning.
2. **HTTP Failures & Rate Limits:**
   - **404 Handling:** Directly captured to identify mistyped, missing, or private repositories.
   - **403/429 Rate Limiting Parsing:** GitHub returns a `X-RateLimit-Reset` header containing a Unix timestamp of when the rate limit refreshes. If the client encounters a rate limit block, it parses this header to show a human-readable countdown in local time (`YYYY-MM-DD HH:MM:SS`), explaining exactly when they can resume using the CLI. It also guides them on setting `GITHUB_TOKEN` for instant unblocking.
3. **Pre-Network Input Validation:**
   - Avoids making wasteful API requests for obviously invalid arguments.
   - Matches a strict regular expression `^[a-zA-Z0-9\-]+/[a-zA-Z0-9\-_.]+$` to block spaces, trailing slashes, empty strings, or symbols before they hit the network.

---

## 4. Scaling Considerations (Handling 1,000 Repositories)

If this CLI tool were to scale to process 1,000+ repositories in a batch pipeline, we would evolve the design as follows:

1. **Asynchronous Parallel Fetching (`httpx` + `asyncio`):**
   - Sequential requests would take hours. Transitioning to an async client like `httpx` allows running up to 50 concurrent fetch workers, completing the pipeline in less than 2 minutes.
2. **Token Rotation & Authentication:**
   - A single token would rate limit quickly (5,000 requests/hr is only enough for ~1,250 repos, since each repo requires 4 endpoints: metadata, languages, contributors, commits).
   - We would implement a **Token Pool Manager** that rotates through multiple GitHub Personal Access Tokens and monitors their rate limit headers dynamically.
3. **Queueing & Rate Limit Backoff:**
   - Implement exponential backoff with jitter when encountering a `429 Too Many Requests` or `403 secondary rate limits`.
4. **Caching Layer:**
   - Store results in a local SQLite or Redis cache with a 1-day TTL. If a repo has not been pushed to since the last scan (checked quickly via a lightweight `ETag` or `If-Modified-Since` request), we serve its detailed statistics from the cache, saving rate limits and network bandwidth.
