import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from scripts import production_readiness_check


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text

    def json(self):
        return self._payload


def test_frontend_routes_are_checked(monkeypatch):
    requested_urls = []

    def fake_get(url, **_kwargs):
        requested_urls.append(url)
        return FakeResponse(200)

    monkeypatch.setattr(production_readiness_check.requests, "get", fake_get)

    findings = production_readiness_check.check_frontend_routes(
        "http://127.0.0.1:3000",
        ["/", "/fleet", "/operations"],
    )

    assert findings == []
    assert requested_urls == [
        "http://127.0.0.1:3000/",
        "http://127.0.0.1:3000/fleet",
        "http://127.0.0.1:3000/operations",
    ]


def test_frontend_route_failure_prevents_ready(monkeypatch):
    def fake_get(url, **_kwargs):
        if url.endswith("/health"):
            return FakeResponse(200, {"env": {"status": "healthy"}})
        if url.endswith("/fleet"):
            return FakeResponse(500)
        return FakeResponse(200)

    monkeypatch.setattr(production_readiness_check.requests, "get", fake_get)

    findings = production_readiness_check.check_frontend_routes(
        "http://127.0.0.1:3000",
        ["/", "/fleet", "/operations"],
    )

    assert findings == ["frontend route /fleet returned HTTP 500"]


def test_frontend_route_manifest_failure_gets_repair_hint(monkeypatch):
    def fake_get(url, **_kwargs):
        if url.endswith("/"):
            return FakeResponse(
                500,
                text='Could not find the module "global-error.js#default" in the React Client Manifest',
            )
        return FakeResponse(200)

    monkeypatch.setattr(production_readiness_check.requests, "get", fake_get)

    findings = production_readiness_check.check_frontend_routes(
        "http://127.0.0.1:3000",
        ["/"],
    )

    assert findings == [
        "frontend route / returned HTTP 500"
        " (Next.js client manifest appears stale; clear workbench_ui\\.next\\dev "
        "with scripts\\workbench_frontend_preflight.py --mode development --repair-cache and restart the frontend)"
    ]


def test_backend_health_reports_unavailable(monkeypatch):
    def fake_get(_url, **_kwargs):
        raise TimeoutError("connect timed out")

    monkeypatch.setattr(production_readiness_check.requests, "get", fake_get)

    findings = production_readiness_check.check_backend_health("http://127.0.0.1:8000", "test-key")

    assert findings == ["live backend startup check unavailable: connect timed out"]


def test_backend_health_reports_degraded_environment(monkeypatch):
    monkeypatch.setattr(
        production_readiness_check.requests,
        "get",
        lambda *_args, **_kwargs: FakeResponse(200, {"env": {"status": "degraded"}}),
    )

    findings = production_readiness_check.check_backend_health("http://127.0.0.1:8000", "test-key")

    assert findings == ["environment health is degraded"]
