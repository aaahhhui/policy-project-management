from __future__ import annotations

import hashlib
import io
import json
import tarfile
from pathlib import Path

from scripts.recover_backup import restore_backup


class DrillRunner:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], dict[str, str], bytes | None]] = []

    def target_resources(self, _project_name: str, _environment: dict[str, str]) -> set[str]:
        return set()

    def run(
        self,
        arguments: tuple[str, ...],
        *,
        environment: dict[str, str],
        input_path: Path | None = None,
        timeout_seconds: int,
    ) -> str:
        self.calls.append((arguments, environment, input_path))
        if "recovery-health" in arguments[-1]:
            return "ok"
        if "recovery-verification" in arguments[-1]:
            return '{"policies":4,"projects":2,"files":1}'
        return ""


def _entry(path: str, content: bytes) -> dict[str, object]:
    return {"path": path, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def _complete_set(root: Path) -> str:
    backup_set = root / "sets" / "21-20260820T033000Z"
    backup_set.mkdir(parents=True)
    dump = b"CREATE TABLE policies (id int);"
    archive_buffer = io.BytesIO()
    with tarfile.open(fileobj=archive_buffer, mode="w") as archive:
        info = tarfile.TarInfo("captured/policy.html")
        info.size = 4
        archive.addfile(info, io.BytesIO(b"page"))
    archive = archive_buffer.getvalue()
    (backup_set / "database.sql").write_bytes(dump)
    (backup_set / "files.tar").write_bytes(archive)
    (backup_set / "manifest.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "completed_at": "2026-08-20T03:30:00+00:00",
                "files": [_entry("database.sql", dump), _entry("files.tar", archive)],
            }
        ),
        encoding="utf-8",
    )
    return "sets/21-20260820T033000Z"


def test_recovery_drill_uses_real_manifest_and_safe_orchestration(tmp_path: Path) -> None:
    runner = DrillRunner()

    report = restore_backup(tmp_path, _complete_set(tmp_path), "stage5-recovery-uat", runner)

    commands = [call[0] for call in runner.calls]
    assert "recovery-health" in commands[-2][-1]
    assert "recovery-verification" in commands[-1][-1]
    assert commands[0][-3:] == ("up", "-d", "mysql")
    assert commands[4][-3:] == ("up", "-d", "api")
    report_json = json.dumps(report.as_dict())
    assert str(tmp_path) not in report_json
    assert "CREATE TABLE" not in report_json
