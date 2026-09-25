from threading import Event

import pytest
from fastapi import HTTPException

from app.api.limits import RequestLimits


def test_total_quota_applies_across_users():
    limits = RequestLimits(per_minute=10, concurrent=1, total_per_minute=2)
    limits.check_user("a")
    limits.check_user("b")
    with pytest.raises(HTTPException) as error:
        limits.check_user("c")
    assert error.value.status_code == 429


def test_timeout_keeps_slot_until_upstream_finishes(api, make_token):
    from app.api.limits import RequestLimits

    api.app.state.settings.request_timeout_seconds = 0.02
    api.app.state.limits = RequestLimits(per_minute=10, concurrent=1)
    finish = Event()
    stopped = Event()

    def work(*_):
        try:
            assert finish.wait(5)
            return {"answer": "late", "sources": []}
        finally:
            stopped.set()

    api.service.answer.side_effect = work
    auth = {"Authorization": "Bearer " + make_token()}
    try:
        assert (
            api.client.post(
                "/api/chat", json={"question": "x"}, headers=auth
            ).status_code
            == 504
        )
        assert api.client.get("/health/live").status_code == 200
        assert (
            api.client.post(
                "/api/chat", json={"question": "x"}, headers=auth
            ).status_code
            == 429
        )
    finally:
        finish.set()
        assert stopped.wait(5)
