"""Dashboard CORS tests."""

from __future__ import annotations

import re

from backend.app.main import _dashboard_cors_origin_regex


def test_dashboard_cors_regex_allows_tailscale_dashboard_port() -> None:
    regex = _dashboard_cors_origin_regex(5176, 5173)

    assert re.match(regex, "http://100.66.71.112:5176")
    assert re.match(regex, "http://127.0.0.1:5176")
    # Also allows the app's own dev port, not just the dashboard's.
    assert re.match(regex, "http://100.66.71.112:5173")
    assert not re.match(regex, "http://100.66.71.112:5177")
    assert not re.match(regex, "http://example.com:5176")
