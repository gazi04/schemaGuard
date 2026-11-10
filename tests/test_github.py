import json
from collections.abc import Callable

import httpx
import pytest

from schemaguard.github import (
    Comment,
    GitHubError,
    find_comment,
    make_client,
    post_comment,
)
from schemaguard.report import MARKER

REPO = "acme/shop"
BODY = f"{MARKER}\n## SchemaGuard"
COMMENTS_PATH = f"/repos/{REPO}/issues/7/comments"

Handler = Callable[[httpx.Request], httpx.Response]


def client_for(handler: Handler) -> httpx.Client:
    return httpx.Client(
        base_url="https://api.github.com", transport=httpx.MockTransport(handler)
    )


def comment(id: int, body: str) -> dict[str, object]:
    return {"id": id, "body": body, "user": {"login": "someone"}}


def recorder(existing: list[dict[str, object]]):
    """Handler serving `existing` on GET and recording every request."""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method == "GET":
            return httpx.Response(200, json=existing)
        return httpx.Response(200, json={})

    return handler, seen


def test_find_comment_matches_marker_at_start():
    comments = [Comment(id=1, body="hi"), Comment(id=2, body=BODY)]
    found = find_comment(comments, MARKER)
    assert found is not None
    assert found.id == 2


def test_find_comment_none_when_missing_or_empty():
    assert find_comment([], MARKER) is None
    assert find_comment([Comment(id=1, body="hi")], MARKER) is None


def test_find_comment_ignores_marker_not_at_start():
    quoted = Comment(id=1, body=f"> {MARKER}")
    assert find_comment([quoted], MARKER) is None


def test_find_comment_first_wins():
    comments = [Comment(id=3, body=BODY), Comment(id=4, body=BODY)]
    found = find_comment(comments, MARKER)
    assert found is not None
    assert found.id == 3


def test_post_comment_creates_when_none():
    handler, seen = recorder([comment(1, "unrelated")])
    with client_for(handler) as client:
        assert post_comment(client, REPO, 7, BODY) == "created"
    assert [r.method for r in seen] == ["GET", "POST"]
    assert seen[1].url.path == COMMENTS_PATH
    assert json.loads(seen[1].content) == {"body": BODY}


def test_post_comment_updates_existing():
    handler, seen = recorder([comment(1, "unrelated"), comment(42, f"{MARKER}\nold")])
    with client_for(handler) as client:
        assert post_comment(client, REPO, 7, BODY) == "updated"
    assert [r.method for r in seen] == ["GET", "PATCH"]
    assert seen[1].url.path == f"/repos/{REPO}/issues/comments/42"
    assert json.loads(seen[1].content) == {"body": BODY}


def test_post_comment_follows_pagination():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.method != "GET":
            return httpx.Response(200, json={})
        if request.url.params.get("page") == "2":
            return httpx.Response(200, json=[comment(99, f"{MARKER}\nold")])
        link = (
            f'<https://api.github.com{COMMENTS_PATH}?per_page=100&page=2>; rel="next"'
        )
        return httpx.Response(
            200, json=[comment(1, "unrelated")], headers={"Link": link}
        )

    with client_for(handler) as client:
        assert post_comment(client, REPO, 7, BODY) == "updated"
    assert [r.method for r in seen] == ["GET", "GET", "PATCH"]
    assert seen[0].url.params.get("per_page") == "100"
    assert seen[2].url.path.endswith("/comments/99")


@pytest.mark.parametrize("status", [401, 403, 404])
def test_permission_errors_include_hint(status: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"message": "nope"})

    with client_for(handler) as client:
        with pytest.raises(GitHubError, match=f"{status}.*pull-requests: write"):
            post_comment(client, REPO, 7, BODY)


def test_server_error_has_no_hint():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500)

    with client_for(handler) as client:
        with pytest.raises(GitHubError, match="500") as info:
            post_comment(client, REPO, 7, BODY)
    assert "pull-requests" not in str(info.value)


def test_network_error_becomes_github_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    with client_for(handler) as client:
        with pytest.raises(GitHubError, match="could not reach GitHub"):
            post_comment(client, REPO, 7, BODY)


def test_unexpected_response_shape_becomes_github_error():
    def bad(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"nope": 1}])

    with client_for(bad) as client:
        with pytest.raises(GitHubError, match="unexpected"):
            post_comment(client, REPO, 7, BODY)


def test_make_client_sets_headers_and_hides_token_in_errors():
    client = make_client("secret-token")
    assert client.headers["Authorization"] == "Bearer secret-token"
    assert client.headers["Accept"] == "application/vnd.github+json"
    assert str(client.base_url).startswith("https://api.github.com")
    client.close()


def test_post_comment_create_false_skips_when_missing():
    handler, seen = recorder([comment(1, "unrelated")])
    with client_for(handler) as client:
        assert post_comment(client, REPO, 7, BODY, create=False) == "skipped"
    assert [r.method for r in seen] == ["GET"]


def test_post_comment_create_false_still_updates():
    handler, seen = recorder([comment(42, f"{MARKER}\nold")])
    with client_for(handler) as client:
        assert post_comment(client, REPO, 7, BODY, create=False) == "updated"
    assert [r.method for r in seen] == ["GET", "PATCH"]
