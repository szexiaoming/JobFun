"""Validate staging/production configuration without exposing secret values."""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from typing import Literal
from urllib.parse import urlsplit

from dotenv import dotenv_values

from src.ops.maintenance_export_integrity import parse_hmac_keyring


Level = Literal["pass", "warning", "failure"]


@dataclass(frozen=True, slots=True)
class CheckResult:
    name: str
    level: Level
    message: str


@dataclass(frozen=True, slots=True)
class PreflightReport:
    ready: bool
    checks: tuple[CheckResult, ...]

    def as_dict(self) -> dict:
        return {
            "ready": self.ready,
            "summary": {
                "passed": sum(check.level == "pass" for check in self.checks),
                "warnings": sum(check.level == "warning" for check in self.checks),
                "failures": sum(check.level == "failure" for check in self.checks),
            },
            "checks": [asdict(check) for check in self.checks],
        }


def evaluate_preflight(environment: Mapping[str, str], *, strict: bool = False) -> PreflightReport:
    """Return a redacted release-readiness report for an environment mapping."""
    checks: list[CheckResult] = []
    deployment_env = _value(environment, "JOBFUN_API_ENV").lower()
    checks.append(_choice("api_environment", deployment_env, {"staging", "production"}))

    checks.append(_equals("database_backend", _value(environment, "DATABASE_BACKEND"), "postgres"))
    dsn = _value(environment, "POSTGRES_DSN")
    checks.append(
        CheckResult(
            "postgres_dsn",
            "pass" if _valid_postgres_dsn(dsn) else "failure",
            "PostgreSQL DSN is configured with a supported scheme."
            if _valid_postgres_dsn(dsn)
            else "Set POSTGRES_DSN to a postgresql:// or postgres:// connection URI.",
        )
    )

    checks.append(_equals("object_storage_backend", _value(environment, "OBJECT_STORAGE_BACKEND"), "s3"))
    checks.append(_required("s3_bucket", _value(environment, "S3_BUCKET"), "Configure a private S3 bucket name."))
    checks.append(_required("s3_region", _value(environment, "S3_REGION"), "Configure the S3 region."))

    checks.append(_boolean("secure_cookie", _value(environment, "JOBFUN_COOKIE_SECURE"), expected=True))
    checks.append(_equals("structured_logs", _value(environment, "JOBFUN_LOG_FORMAT"), "json"))
    worker_name = _value(environment, "JOBFUN_WORKER_NAME")
    checks.append(
        CheckResult(
            "worker_identity",
            "pass" if worker_name and worker_name.lower() != "default" else "failure",
            "A stable, non-default worker identity is configured."
            if worker_name and worker_name.lower() != "default"
            else "Set JOBFUN_WORKER_NAME to a stable, environment-specific value.",
        )
    )
    checks.extend(_threshold_checks(environment))
    checks.append(_maintenance_export_authentication(environment))

    provider = _value(environment, "AI_PROVIDER").lower()
    checks.append(_choice("ai_provider", provider, {"deepseek", "anthropic"}))
    provider_key = {
        "deepseek": _value(environment, "DEEPSEEK_API_KEY"),
        "anthropic": _value(environment, "ANTHROPIC_API_KEY"),
    }.get(provider, "")
    checks.append(_required("ai_provider_credential", provider_key, "Configure the selected AI provider credential."))

    api_base_url = _value(environment, "JOBFUN_API_BASE_URL")
    checks.append(_url_check("web_api_base_url", api_base_url, require_https=deployment_env == "production"))

    webhook = _value(environment, "JOBFUN_ALERT_WEBHOOK_URL")
    checks.append(
        _url_check("alert_webhook", webhook, require_https=True)
        if webhook
        else CheckResult(
            "alert_webhook",
            "warning",
            "No failure alert webhook is configured; use a non-production test channel before release.",
        )
    )

    if _value(environment, "OPENAI_API_KEY"):
        checks.append(CheckResult("speech_transcription", "pass", "Optional speech transcription is configured."))
    else:
        checks.append(
            CheckResult(
                "speech_transcription",
                "warning",
                "OPENAI_API_KEY is absent; voice transcription will remain unavailable.",
            )
        )

    blocking_levels = {"failure", "warning"} if strict else {"failure"}
    return PreflightReport(
        ready=not any(check.level in blocking_levels for check in checks),
        checks=tuple(checks),
    )


def _value(environment: Mapping[str, str], name: str) -> str:
    return str(environment.get(name, "") or "").strip()


def _equals(name: str, value: str, expected: str) -> CheckResult:
    ok = value.lower() == expected
    return CheckResult(
        name,
        "pass" if ok else "failure",
        f"Configured value is {expected}." if ok else f"Set this value to {expected}.",
    )


def _choice(name: str, value: str, choices: set[str]) -> CheckResult:
    ok = value in choices
    allowed = ", ".join(sorted(choices))
    return CheckResult(
        name,
        "pass" if ok else "failure",
        "Configured value is supported." if ok else f"Set this value to one of: {allowed}.",
    )


def _required(name: str, value: str, missing_message: str) -> CheckResult:
    return CheckResult(
        name,
        "pass" if bool(value) else "failure",
        "Required value is present." if value else missing_message,
    )


def _boolean(name: str, value: str, *, expected: bool) -> CheckResult:
    expected_text = "true" if expected else "false"
    ok = value.lower() == expected_text
    return CheckResult(
        name,
        "pass" if ok else "failure",
        f"Configured value is {expected_text}." if ok else f"Set this value to {expected_text}.",
    )


def _valid_postgres_dsn(value: str) -> bool:
    try:
        parsed = urlsplit(value)
    except ValueError:
        return False
    return parsed.scheme in {"postgres", "postgresql"} and bool(parsed.hostname and parsed.path.strip("/"))


def _url_check(name: str, value: str, *, require_https: bool) -> CheckResult:
    try:
        parsed = urlsplit(value)
    except ValueError:
        parsed = None
    allowed = {"https"} if require_https else {"http", "https"}
    ok = bool(parsed and parsed.scheme in allowed and parsed.hostname)
    return CheckResult(
        name,
        "pass" if ok else "failure",
        "A valid service URL is configured."
        if ok
        else f"Configure a valid {'HTTPS' if require_https else 'HTTP(S)'} URL.",
    )


def _threshold_checks(environment: Mapping[str, str]) -> list[CheckResult]:
    specs = (
        ("worker_heartbeat_threshold", "JOBFUN_WORKER_HEARTBEAT_MAX_AGE_SECONDS", 30, 600, "seconds"),
        ("worker_queue_threshold", "JOBFUN_WORKER_QUEUE_MAX_AGE_SECONDS", 60, 3600, "seconds"),
        ("worker_stale_threshold", "JOBFUN_WORKER_RUNNING_STALE_SECONDS", 120, 7200, "seconds"),
        ("retained_audio_policy", "JOBFUN_RETAINED_AUDIO_MAX_DAYS", 1, 365, "days"),
        ("audio_cleanup_schedule", "JOBFUN_AUDIO_CLEANUP_MAX_AGE_HOURS", 1, 168, "hours"),
        ("audio_cleanup_runtime", "JOBFUN_AUDIO_CLEANUP_STALE_SECONDS", 60, 7200, "seconds"),
        ("audio_cleanup_failures", "JOBFUN_AUDIO_CLEANUP_FAILURE_THRESHOLD", 1, 20, "runs"),
        ("maintenance_history", "JOBFUN_MAINTENANCE_HISTORY_MAX_ROWS", 12, 1000, "rows"),
    )
    results = []
    for name, variable, minimum, maximum, unit in specs:
        raw = _value(environment, variable)
        try:
            value = int(raw)
        except ValueError:
            value = -1
        ok = minimum <= value <= maximum
        results.append(
            CheckResult(
                name,
                "pass" if ok else "failure",
                f"Threshold is within the supported {minimum}-{maximum} {unit} range."
                if ok
                else f"Set {variable} to an integer from {minimum} to {maximum}.",
            )
        )
    return results


def _maintenance_export_authentication(
    environment: Mapping[str, str],
) -> CheckResult:
    active_key_id = _value(environment, "JOBFUN_MAINTENANCE_EXPORT_ACTIVE_KEY_ID")
    encoded_keyring = _value(environment, "JOBFUN_MAINTENANCE_EXPORT_HMAC_KEYS_JSON")
    if not active_key_id and not encoded_keyring:
        return CheckResult(
            "maintenance_export_authentication",
            "pass",
            "Optional authenticated maintenance exports are disabled.",
        )
    if not active_key_id or not encoded_keyring:
        return CheckResult(
            "maintenance_export_authentication",
            "failure",
            "Configure both the active key ID and HMAC keyring.",
        )
    try:
        keyring = parse_hmac_keyring(encoded_keyring)
    except ValueError:
        return CheckResult(
            "maintenance_export_authentication",
            "failure",
            "Configure a valid Base64 HMAC keyring with 32-64 byte keys.",
        )
    if active_key_id not in keyring:
        return CheckResult(
            "maintenance_export_authentication",
            "failure",
            "The active HMAC key ID is not present in the configured keyring.",
        )
    return CheckResult(
        "maintenance_export_authentication",
        "pass",
        "The active HMAC key is available for authenticated exports.",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate JobFun release configuration without printing values.")
    parser.add_argument(
        "--env-file",
        default=".env",
        help="Environment file to validate before process-level overrides (default: .env).",
    )
    parser.add_argument("--json", action="store_true", help="Print a machine-readable report.")
    parser.add_argument("--strict", action="store_true", help="Treat optional warnings as blocking.")
    args = parser.parse_args(argv)
    environment = {
        key: str(value)
        for key, value in dotenv_values(args.env_file).items()
        if value is not None
    }
    environment.update(os.environ)
    report = evaluate_preflight(environment, strict=args.strict)
    payload = report.as_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for check in report.checks:
            print(f"[{check.level.upper():7}] {check.name}: {check.message}")
        print("READY" if report.ready else "NOT READY")
    return 0 if report.ready else 1


if __name__ == "__main__":
    raise SystemExit(main())

