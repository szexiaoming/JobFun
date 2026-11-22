"""Safe maintenance export, authentication, and history retention tests."""

import base64
import json
from datetime import datetime, timedelta, timezone

import pytest

import src.ops.export_maintenance as export_module
from src.db.sqlite_client import Database
from src.ops.export_maintenance import build_maintenance_export, write_export
from src.ops.maintenance_export_integrity import (
    MAX_EXPORT_BYTES,
    attach_integrity,
    load_document,
    parse_hmac_keyring,
    verify_document,
)
from src.ops.verify_maintenance_export import main as verify_main
from src.repositories.maintenance import (
    MaintenanceRunRepository,
    RetentionPolicyRepository,
)
from src.services.audio_retention import RETAINED_AUDIO_POLICY
from src.services.maintenance_monitoring import AUDIO_RETENTION_TASK


def test_configured_history_boundary_prunes_and_exports_only_safe_records(tmp_path):
    database = Database(tmp_path / "maintenance-export.db")
    runs = MaintenanceRunRepository(database, history_max_rows=12)
    policies = RetentionPolicyRepository(database)
    now = datetime(2026, 11, 22, 9, tzinfo=timezone.utc)

    for index in range(15):
        completed_at = (now + timedelta(minutes=index)).isoformat()
        runs.start(AUDIO_RETENTION_TASK, completed_at)
        runs.finish(
            AUDIO_RETENTION_TASK,
            completed_at=completed_at,
            checked=index,
            deleted=index // 2,
            failed=0,
        )
    policies.observe(RETAINED_AUDIO_POLICY, 30, now.isoformat())
    policies.observe(
        RETAINED_AUDIO_POLICY,
        45,
        (now + timedelta(hours=1)).isoformat(),
    )

    payload = build_maintenance_export(
        database,
        history_limit=12,
        retention_days=45,
        now=lambda: now,
    )
    serialized = json.dumps(payload)

    assert payload["schema_version"] == 3
    assert payload["history_limit"] == 12
    assert len(payload["run_history"]) == 12
    assert payload["run_history"][-1]["checked_count"] == 3
    assert payload["run_history"][0]["checked_count"] == 14
    assert payload["retention_policy"]["changes"][0]["previous_days"] == 30
    assert payload["retention_policy"]["changes"][0]["new_days"] == 45
    for forbidden in ("user_id", "object_key", "original_name", "answer_text"):
        assert forbidden not in serialized
    assert payload["integrity"]["algorithm"] == "sha256"
    assert payload["authentication"] is None
    assert verify_document(payload).valid is True
    database.close()


def test_export_creates_new_json_file_without_overwriting(tmp_path):
    target = tmp_path / "maintenance.json"
    payload = {"schema_version": 1, "run_history": []}

    write_export(payload, str(target))

    assert json.loads(target.read_text(encoding="utf-8")) == payload
    with pytest.raises(FileExistsError):
        write_export(payload, str(target))


def test_checksum_detects_modified_export(tmp_path):
    database = Database(tmp_path / "modified-export.db")
    payload = build_maintenance_export(
        database,
        history_limit=12,
        retention_days=30,
    )
    payload["history_limit"] = 13

    report = verify_document(payload)

    assert report.valid is False
    assert "Integrity checksum does not match" in " ".join(report.errors)
    database.close()


def test_recomputed_checksum_does_not_bypass_sensitive_field_validation(tmp_path):
    database = Database(tmp_path / "forbidden-export.db")
    payload = build_maintenance_export(
        database,
        history_limit=12,
        retention_days=30,
    )
    unsigned = {key: value for key, value in payload.items() if key != "integrity"}
    unsigned["user_id"] = 1
    forged = attach_integrity(unsigned)

    report = verify_document(forged)

    assert report.valid is False
    assert "forbidden sensitive field" in " ".join(report.errors)
    database.close()


def test_offline_verifier_accepts_valid_file_and_rejects_modified_file(tmp_path, capsys):
    database = Database(tmp_path / "offline-verify.db")
    target = tmp_path / "maintenance.json"
    payload = build_maintenance_export(
        database,
        history_limit=12,
        retention_days=30,
    )
    write_export(payload, str(target))

    assert verify_main([str(target)]) == 0
    assert "VALID" in capsys.readouterr().out

    assert verify_main([str(target), "--require-authentication"]) == 1
    assert "Authenticated export is required" in capsys.readouterr().err

    modified = json.loads(target.read_text(encoding="utf-8"))
    modified["history_limit"] = 13
    target.write_text(json.dumps(modified), encoding="utf-8")
    assert verify_main([str(target)]) == 1
    assert "checksum does not match" in capsys.readouterr().err
    database.close()


def test_offline_loader_rejects_oversized_file(tmp_path):
    target = tmp_path / "oversized.json"
    target.write_bytes(b" " * (MAX_EXPORT_BYTES + 1))

    with pytest.raises(ValueError, match="exceeds"):
        load_document(target)


def test_offline_loader_rejects_duplicate_json_keys(tmp_path):
    target = tmp_path / "duplicate.json"
    target.write_text('{"schema_version": 3, "schema_version": 3}', encoding="utf-8")

    with pytest.raises(ValueError, match="valid UTF-8 JSON"):
        load_document(target)


def test_hmac_authentication_supports_key_rotation_and_rejects_wrong_key(tmp_path):
    database = Database(tmp_path / "authenticated-export.db")
    old_key = b"o" * 32
    new_key = b"n" * 32
    old_export = build_maintenance_export(
        database,
        history_limit=12,
        retention_days=30,
        authentication_key_id="2026-q3",
        authentication_key=old_key,
    )
    new_export = build_maintenance_export(
        database,
        history_limit=12,
        retention_days=30,
        authentication_key_id="2026-q4",
        authentication_key=new_key,
    )
    keyring = {"2026-q3": old_key, "2026-q4": new_key}

    assert verify_document(
        old_export,
        authentication_keys=keyring,
        require_authentication=True,
    ).valid is True
    assert verify_document(
        new_export,
        authentication_keys=keyring,
        require_authentication=True,
    ).valid is True
    wrong = verify_document(
        new_export,
        authentication_keys={"2026-q4": b"x" * 32},
        require_authentication=True,
    )
    assert wrong.valid is False
    assert "Authentication digest does not match" in " ".join(wrong.errors)
    assert base64.b64encode(new_key).decode() not in json.dumps(new_export)
    database.close()


def test_keyring_parser_accepts_rotation_set_without_exposing_keys():
    encoded = json.dumps({
        "2026-q3": base64.b64encode(b"o" * 32).decode(),
        "2026-q4": base64.b64encode(b"n" * 32).decode(),
    })

    keyring = parse_hmac_keyring(encoded)

    assert keyring == {"2026-q3": b"o" * 32, "2026-q4": b"n" * 32}
    with pytest.raises(ValueError, match="32-64 bytes"):
        parse_hmac_keyring(json.dumps({"short": base64.b64encode(b"x").decode()}))
    with pytest.raises(ValueError, match="JSON object"):
        parse_hmac_keyring('{"duplicate":"eA==","duplicate":"eA=="}')


def test_offline_verifier_authenticates_with_configured_rotation_keyring(
    tmp_path,
    capsys,
    monkeypatch,
):
    database = Database(tmp_path / "authenticated-offline.db")
    target = tmp_path / "authenticated.json"
    key = b"k" * 32
    payload = build_maintenance_export(
        database,
        history_limit=12,
        retention_days=30,
        authentication_key_id="active-key",
        authentication_key=key,
    )
    write_export(payload, str(target))
    monkeypatch.setattr(
        "config.MAINTENANCE_EXPORT_HMAC_KEYS_JSON",
        json.dumps({"active-key": base64.b64encode(key).decode()}),
    )

    assert verify_main([str(target), "--require-authentication"]) == 0
    assert "VALID" in capsys.readouterr().out
    database.close()


def test_export_cli_uses_active_key_without_writing_key_material(
    tmp_path,
    monkeypatch,
):
    database = Database(tmp_path / "authenticated-cli.db")
    target = tmp_path / "cli-export.json"
    key = b"s" * 32
    encoded_key = base64.b64encode(key).decode()
    monkeypatch.setattr(export_module, "_database", lambda: database)
    monkeypatch.setattr(
        export_module.config,
        "MAINTENANCE_EXPORT_ACTIVE_KEY_ID",
        "active-key",
    )
    monkeypatch.setattr(
        export_module.config,
        "MAINTENANCE_EXPORT_HMAC_KEYS_JSON",
        json.dumps({"active-key": encoded_key}),
    )

    assert export_module.main(["--authenticate", "--output", str(target)]) == 0
    document = load_document(target)
    assert document["authentication"]["key_id"] == "active-key"
    assert encoded_key not in target.read_text(encoding="utf-8")
    assert verify_document(
        document,
        authentication_keys={"active-key": key},
        require_authentication=True,
    ).valid is True


@pytest.mark.parametrize("history_limit", [0, 11, 1001])
def test_export_rejects_unsupported_history_limits(tmp_path, history_limit):
    database = Database(tmp_path / f"invalid-{history_limit}.db")
    with pytest.raises(ValueError, match="between 12 and 1000"):
        build_maintenance_export(
            database,
            history_limit=history_limit,
            retention_days=30,
        )
    database.close()
