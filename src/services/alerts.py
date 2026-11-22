"""Safe operational failure alerts with an optional webhook sink."""

from __future__ import annotations

import json
import urllib.request
from typing import Protocol

import config


class AlertSink(Protocol):
    def send(self, event: dict) -> None: ...


class NullAlertSink:
    def send(self, event: dict) -> None:
        return None


class WebhookAlertSink:
    def __init__(
        self,
        url: str,
        *,
        bearer_token: str = "",
        timeout: float = 5.0,
        opener=None,
    ) -> None:
        if not str(url or "").startswith(("https://", "http://")):
            raise ValueError("Alert webhook must use HTTP or HTTPS")
        self._url = str(url)
        self._token = str(bearer_token or "")
        self._timeout = max(0.1, float(timeout))
        self._opener = opener or urllib.request.urlopen

    def send(self, event: dict) -> None:
        payload = _safe_event(event)
        headers = {"Content-Type": "application/json", "User-Agent": "JobFun-Worker/1"}
        if self._token:
            headers["Authorization"] = f"Bearer {self._token}"
        request = urllib.request.Request(
            self._url,
            data=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        with self._opener(request, timeout=self._timeout) as response:
            if int(getattr(response, "status", 200)) >= 400:
                raise RuntimeError("Alert webhook rejected the event")


def configured_alert_sink() -> AlertSink:
    if not config.ALERT_WEBHOOK_URL:
        return NullAlertSink()
    return WebhookAlertSink(
        config.ALERT_WEBHOOK_URL,
        bearer_token=config.ALERT_WEBHOOK_BEARER_TOKEN,
        timeout=config.ALERT_WEBHOOK_TIMEOUT_SECONDS,
    )


def _safe_event(event: dict) -> dict:
    allowed = {
        "event_type",
        "severity",
        "operation_id",
        "operation_type",
        "error_code",
        "retry_count",
        "occurred_at",
        "maintenance_task",
        "checked_count",
        "deleted_count",
        "failed_count",
        "consecutive_failures",
    }
    return {key: event[key] for key in allowed if key in event}
