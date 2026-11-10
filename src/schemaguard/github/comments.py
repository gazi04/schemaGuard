from collections.abc import Iterable
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict

from schemaguard.report import MARKER

API_URL = "https://api.github.com"

PERMISSION_HINT = (
    "check that the token has `pull-requests: write` "
    "and that the repository and PR number are correct"
)


class GitHubError(Exception):
    """Any failure talking to GitHub (network, HTTP status, bad response)."""


class Comment(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: int
    body: str


def make_client(token: str, base_url: str = API_URL) -> httpx.Client:
    """Client with auth headers. The caller closes it (use `with`)."""
    return httpx.Client(
        base_url=base_url,
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        },
        timeout=10,
    )


def find_comment(comments: Iterable[Comment], marker: str) -> Comment | None:
    """First comment whose body starts with the marker, or None."""
    return next((c for c in comments if c.body.startswith(marker)), None)


def send(client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
    """Send a request; every failure becomes a GitHubError."""
    try:
        response = client.request(method, url, **kwargs)
        response.raise_for_status()
    except httpx.HTTPStatusError as e:
        status = e.response.status_code
        message = f"GitHub returned {status} for {method} {e.request.url.path}"
        if status in (401, 403, 404):
            message += f": {PERMISSION_HINT}"
        raise GitHubError(message) from e
    except httpx.RequestError as e:
        raise GitHubError(f"could not reach GitHub: {e}") from e
    return response


def list_comments(client: httpx.Client, repo: str, pr: int) -> list[Comment]:
    """All comments on a PR, following pagination."""
    comments: list[Comment] = []
    url: str | None = f"/repos/{repo}/issues/{pr}/comments"
    params: dict[str, int] | None = {"per_page": 100}
    while url:
        response = send(client, "GET", url, params=params)
        try:
            comments.extend(Comment.model_validate(item) for item in response.json())
        except ValueError as e:
            raise GitHubError("GitHub returned an unexpected comment list") from e
        # The next-page URL already carries its query string.
        url = response.links.get("next", {}).get("url")
        params = None
    return comments


def create_comment(client: httpx.Client, repo: str, pr: int, body: str) -> None:
    send(client, "POST", f"/repos/{repo}/issues/{pr}/comments", json={"body": body})


def update_comment(client: httpx.Client, repo: str, comment_id: int, body: str) -> None:
    send(
        client,
        "PATCH",
        f"/repos/{repo}/issues/comments/{comment_id}",
        json={"body": body},
    )


def post_comment(
    client: httpx.Client, repo: str, pr: int, body: str, *, create: bool = True
) -> Literal["created", "updated", "skipped"]:
    """Update the SchemaGuard comment on the PR, or create it.

    With create=False a missing comment is not created ("skipped"), so an
    empty report never adds noise but can still clear an outdated comment.
    """
    existing = find_comment(list_comments(client, repo, pr), MARKER)
    if existing is not None:
        update_comment(client, repo, existing.id, body)
        return "updated"
    if not create:
        return "skipped"
    create_comment(client, repo, pr, body)
    return "created"
