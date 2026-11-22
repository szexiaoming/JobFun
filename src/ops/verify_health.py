"""Read-only health verification for an explicitly selected JobFun environment."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict, dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin, urlsplit
from urllib.request import Request, urlopen


@dataclass(frozen=True, slots=True)
class HealthCheck:
    endpoint: str
    ok: bool
    status_code: int | None
    message: str


def verify_health(base_url: str, *, opener=urlopen, timeout: float = 5.0) -> tuple[HealthCheck, ...]:
    """GET public health endpoints without credentials or mutations."""
    normalized = base_url.rstrip("/") + "/"
    parsed = urlsplit(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("base_url must be an absolute HTTP(S) URL")

    results = []
    for endpoint, expected_status in (
        ("health/live", "ok"),
        ("health/ready", "ready"),
        ("health/worker", "healthy"),
        ("health/maintenance", "healthy"),
    ):
        request = Request(urljoin(normalized, endpoint), headers={"Accept": "application/json"})
        try:
            with opener(request, timeout=timeout) as response:
                status_code = int(getattr(response, "status", 200))
                payload = json.loads(response.read().decode("utf-8"))
            actual = str(payload.get("status") or "")
            ok = status_code == 200 and actual == expected_status
            message = "Health contract passed." if ok else "Health response did not match the expected status."
        except HTTPError as exc:
            status_code = exc.code
            ok = False
            message = "Health endpoint returned a non-success status."
        except (URLError, TimeoutError, json.JSONDecodeError, UnicodeDecodeError, OSError):
            status_code = None
            ok = False
            message = "Health endpoint could not be read safely."
        results.append(HealthCheck("/" + endpoint, ok, status_code, message))
    return tuple(results)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Verify JobFun health endpoints using read-only requests.")
    parser.add_argument("--base-url", required=True, help="Explicit API origin, for example https://staging-api.example.test")
    parser.add_argument("--timeout", type=float, default=5.0)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if not 0.1 <= args.timeout <= 30:
        parser.error("--timeout must be between 0.1 and 30 seconds")
    try:
        checks = verify_health(args.base_url, timeout=args.timeout)
    except ValueError as exc:
        parser.error(str(exc))
    if args.json:
        print(json.dumps({"healthy": all(item.ok for item in checks), "checks": [asdict(item) for item in checks]}, indent=2))
    else:
        for item in checks:
            label = "PASS" if item.ok else "FAIL"
            print(f"[{label}] {item.endpoint}: {item.message}")
    return 0 if all(item.ok for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())

