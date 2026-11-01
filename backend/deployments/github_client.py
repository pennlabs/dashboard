"""Thin wrapper around the GitHub REST API, used to describe deployed commits.

Unlike Kubernetes state, a commit never changes, so results are cached here
rather than fetched per request. That matters: GitHub allows 60 unauthenticated
requests an hour, shared with everything else behind the cluster's NAT.

Commit details are decoration, so none of this may break a page. A commit that
can't be fetched is simply left out of the result and the UI shows the bare SHA.
"""

import logging
from typing import Any
from urllib.parse import quote

import requests
from django.conf import settings
from django.core.cache import cache

logger = logging.getLogger(__name__)

API_URL = "https://api.github.com"
ORG = "pennlabs"

# Short: this runs inside a gunicorn sync worker. After one failure `get_commits`
# stops calling GitHub, so a request waits out this timeout at most once.
TIMEOUT_SECONDS = 3

# How long to remember that a repo or commit doesn't exist. Not forever, because
# the likeliest cause is a private repo that a token could later be granted.
MISSING_TTL_SECONDS = 60 * 60

# How long to leave GitHub alone after it fails or rate-limits us.
BACKOFF_TTL_SECONDS = 60
_BACKOFF_KEY = "github:backoff"

_UNCACHED = object()


class GitHubUnavailable(Exception):
    """GitHub didn't answer, as opposed to answering that a commit doesn't exist."""


def _fetch_commit(repo: str, sha: str) -> dict[str, str] | None:
    """One commit's subject line and author, or None if GitHub has no such commit."""
    headers = {
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if settings.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {settings.GITHUB_TOKEN}"

    try:
        res = requests.get(
            f"{API_URL}/repos/{ORG}/{quote(repo, safe='')}/commits/{sha}",
            headers=headers,
            timeout=TIMEOUT_SECONDS,
        )
        # 404: no such repo, or a private one. 409: the repo is empty. 422: no
        # such commit. None of these will be fixed by asking again soon.
        if res.status_code in (404, 409, 422):
            return None
        res.raise_for_status()
        commit = res.json()["commit"]
    except (requests.RequestException, KeyError) as exc:
        raise GitHubUnavailable(str(exc)) from exc

    return {
        "message": commit.get("message", "").partition("\n")[0],
        "author": (commit.get("author") or {}).get("name", ""),
    }


def get_commits(repo: str, shas: list[str]) -> dict[str, Any]:
    """Details for each SHA that could be resolved, keyed by that SHA."""
    commits = {}
    for sha in shas:
        key = f"github:commit:{repo}:{sha}"
        commit = cache.get(key, _UNCACHED)
        if commit is _UNCACHED:
            if cache.get(_BACKOFF_KEY):
                continue
            try:
                commit = _fetch_commit(repo, sha)
            except GitHubUnavailable as exc:
                logger.warning("GitHub lookup failed for %s@%s: %s", repo, sha, exc)
                cache.set(_BACKOFF_KEY, True, BACKOFF_TTL_SECONDS)
                continue
            cache.set(key, commit, None if commit else MISSING_TTL_SECONDS)
        if commit:
            commits[sha] = commit
    return commits
