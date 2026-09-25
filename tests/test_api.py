import time
import pytest


def headers(token):
    return {"Authorization": f"Bearer {token}"}


def test_anonymous_requests_do_not_reach_models(api):
    assert api.client.post("/api/chat", json={"question": "hello"}).status_code == 401
    api.service.answer.assert_not_called()


@pytest.mark.parametrize(
    "claim,value,status",
    [
        ("aud", "another-api", 401),
        ("iss", "https://evil.example/", 401),
        ("exp", 1, 401),
        ("nbf", int(time.time()) + 3600, 401),
        ("scp", "other_scope", 403),
        ("scp", None, 403),
        ("azp", "another-client", 403),
        ("ver", "1.0", 403),
    ],
)
def test_rejects_invalid_or_unauthorized_tokens(api, make_token, claim, value, status):
    response = api.client.post(
        "/api/chat",
        json={"question": "hello"},
        headers=headers(make_token(**{claim: value})),
    )
    assert response.status_code == status
    api.service.answer.assert_not_called()


def test_bad_signature_and_unsigned_token_are_rejected(api, make_token):
    token = make_token()
    segments = token.split(".")
    segments[2] = ("A" if segments[2][0] != "A" else "B") + segments[2][1:]
    for invalid in (".".join(segments), "not-a-token", "x" * 16385):
        assert (
            api.client.post(
                "/api/chat", json={"question": "hello"}, headers=headers(invalid)
            ).status_code
            == 401
        )
    api.service.answer.assert_not_called()


def test_valid_user_gets_answer_and_safe_sources(api, make_token):
    response = api.client.post(
        "/api/chat", json={"question": "  hello  "}, headers=headers(make_token())
    )
    assert response.status_code == 200
    assert response.json()["answer"] == "An answer [1]"
    assert response.json()["sources"][0]["source"] == "guide.pdf"
    assert response.json()["request_id"] == response.headers["x-request-id"]
    assert response.headers["cache-control"] == "no-store"
    api.service.answer.assert_called_once_with("hello", 5)


@pytest.mark.parametrize(
    "payload",
    [
        {"question": " "},
        {"question": "x" * 4001},
        {"question": "x", "top_k": 11},
        {"question": "x", "top_k": "2"},
        {"question": "x", "collection": "private"},
        {"question": "x", "user_id": "other"},
    ],
)
def test_validates_payload_without_echoing_it(api, make_token, payload):
    response = api.client.post("/api/chat", json=payload, headers=headers(make_token()))
    assert response.status_code == 422
    assert "input" not in response.json()["detail"][0]
    api.service.answer.assert_not_called()


def test_request_body_cap_and_cross_origin_rejection(api, make_token):
    token_headers = headers(make_token())
    response = api.client.post("/api/chat", content=b"x" * 32769, headers=token_headers)
    assert response.status_code == 413
    response = api.client.post(
        "/api/chat",
        json={"question": "x"},
        headers={**token_headers, "Origin": "https://evil.example"},
    )
    assert response.status_code == 403
    api.service.answer.assert_not_called()


def test_per_user_quota_does_not_block_another_user(api, make_token):
    for _ in range(2):
        assert (
            api.client.post(
                "/api/chat", json={"question": "x"}, headers=headers(make_token())
            ).status_code
            == 200
        )
    response = api.client.post(
        "/api/chat", json={"question": "x"}, headers=headers(make_token())
    )
    assert response.status_code == 429
    assert "retry-after" in response.headers
    assert (
        api.client.post(
            "/api/chat",
            json={"question": "x"},
            headers=headers(make_token(sub="user-two")),
        ).status_code
        == 200
    )


def test_concurrency_limit(api, make_token):
    slots = api.app.state.limits.slots
    for _ in range(4):
        assert slots.acquire(blocking=False)
    try:
        assert (
            api.client.post(
                "/api/chat", json={"question": "x"}, headers=headers(make_token())
            ).status_code
            == 429
        )
        api.service.answer.assert_not_called()
    finally:
        for _ in range(4):
            slots.release()


def test_upstream_failure_is_not_a_success_or_a_secret_leak(api, make_token, caplog):
    api.service.answer.side_effect = RuntimeError("secret-key-and-private-document")
    response = api.client.post(
        "/api/chat", json={"question": "private-prompt"}, headers=headers(make_token())
    )
    assert response.status_code == 503
    assert "secret-key" not in response.text + caplog.text
    assert "private-prompt" not in caplog.text
    api.service.answer.side_effect = None
    assert (
        api.client.post(
            "/api/chat", json={"question": "retry"}, headers=headers(make_token())
        ).status_code
        == 200
    )


def test_health_checks_and_public_config(api):
    assert api.client.get("/health/live").status_code == 200
    assert api.client.get("/health/ready").status_code == 200
    api.service.ready.side_effect = RuntimeError("private database info")
    assert api.client.get("/health/ready").status_code == 503
    assert api.client.get("/health/live").status_code == 200
    assert set(api.client.get("/api/config").json()) == {
        "clientId",
        "authority",
        "redirectUri",
        "scope",
    }
    assert api.client.get("/docs").status_code == 404
    api.service.answer.assert_not_called()
