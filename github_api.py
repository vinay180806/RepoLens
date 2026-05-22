import os
import time
from datetime import datetime
import requests

class GitHubAPIError(Exception):
    """Base exception for GitHub API errors."""
    pass

class RepositoryNotFoundError(GitHubAPIError):
    """Raised when the repository does not exist (404)."""
    pass

class RateLimitExceededError(GitHubAPIError):
    """Raised when the rate limit has been exceeded (403/429)."""
    def __init__(self, message, reset_time=None, limit=None, remaining=None):
        super().__init__(message)
        self.reset_time = reset_time  # Unix timestamp as float/int or None
        self.limit = limit
        self.remaining = remaining

    @property
    def reset_datetime(self):
        if self.reset_time:
            return datetime.fromtimestamp(float(self.reset_time))
        return None

class APIError(GitHubAPIError):
    """Raised for generic GitHub API responses that indicate failure (e.g. 500)."""
    def __init__(self, message, status_code):
        super().__init__(f"API Error {status_code}: {message}")
        self.status_code = status_code

class NetworkTimeoutError(GitHubAPIError):
    """Raised when a request to GitHub API times out."""
    pass


class GitHubAPIClient:
    """A resilient, clean, and highly robust client to interact with the GitHub REST API."""
    
    BASE_URL = "https://api.github.com"
    TIMEOUT = 5.0  # Crucial: 5 second timeout requirement

    def __init__(self, token=None):
        """
        Initializes the client.
        
        Args:
            token (str, optional): A GitHub Personal Access Token (PAT).
                                   If not provided, attempts to load GITHUB_TOKEN
                                   from environment variables.
        """
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.session = requests.Session()
        
        # Configure headers according to GitHub API standards
        self.session.headers.update({
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "GitHub-Repo-Analyzer-CLI/1.0"
        })
        
        if self.token:
            self.session.headers.update({
                "Authorization": f"token {self.token}"
            })

    def _request(self, endpoint, params=None, retries=2):
        """
        Internal request helper to centralize error handling and timeout requirements.
        Supports automatic retries for transient network/timeout errors.
        """
        url = f"{self.BASE_URL}/{endpoint.lstrip('/')}"
        
        for attempt in range(retries + 1):
            try:
                response = self.session.get(url, params=params, timeout=self.TIMEOUT)
                break  # Success, exit retry loop
            except requests.Timeout as e:
                if attempt < retries:
                    time.sleep(0.5)  # Small backoff before retrying
                    continue
                raise NetworkTimeoutError("The request to GitHub API timed out (5s limit). Please check your internet connection.") from e
            except requests.RequestException as e:
                if attempt < retries:
                    time.sleep(0.5)
                    continue
                raise GitHubAPIError(f"A network error occurred while communicating with GitHub: {e}") from e

        # Handle rate limiting specifically
        limit = response.headers.get("X-RateLimit-Limit")
        remaining = response.headers.get("X-RateLimit-Remaining")
        reset_time = response.headers.get("X-RateLimit-Reset")

        if response.status_code == 403 or response.status_code == 429:
            # Check if it is a rate limit or abuse detection mechanism
            message = response.json().get("message", "Forbidden/Rate limit exceeded")
            if remaining == "0" or "rate limit" in message.lower():
                raise RateLimitExceededError(
                    f"GitHub API rate limit exceeded. {message}",
                    reset_time=reset_time,
                    limit=limit,
                    remaining=remaining
                )
            elif response.status_code == 403:
                raise APIError(f"Access forbidden (403): {message}. Verify permissions or token.", response.status_code)

        if response.status_code == 404:
            raise RepositoryNotFoundError("The repository was not found. Please verify owner/repo spelling.")

        if not response.ok:
            error_data = response.json() if response.content else {}
            message = error_data.get("message", "Unknown API error occurred.")
            raise APIError(message, response.status_code)

        return response.json()

    def get_repo(self, owner, repo):
        """
        Fetches repository metadata.
        """
        return self._request(f"repos/{owner}/{repo}")

    def get_languages(self, owner, repo):
        """
        Fetches repository language distribution.
        """
        return self._request(f"repos/{owner}/{repo}/languages")

    def get_contributors(self, owner, repo):
        """
        Fetches repository contributors (returns top 30 by default).
        """
        return self._request(f"repos/{owner}/{repo}/contributors", params={"per_page": 30})

    def get_last_commits(self, owner, repo, per_page=30):
        """
        Fetches recent commits from the default branch.
        """
        return self._request(f"repos/{owner}/{repo}/commits", params={"per_page": per_page})
