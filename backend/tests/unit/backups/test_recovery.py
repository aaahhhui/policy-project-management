from __future__ import annotations

import hashlib
import io
import json
import tarfile
from datetime import UTC, datetime
from pathlib import Path
import sys
import subprocess
import re
from types import SimpleNamespace

import pytest

from scripts.recover_backup import (
    RecoveryRefused,
    build_recovery_environment,
    build_recovery_plan,
    main,
    restore_backup,
)


class FakeRunner:
    def __init__(
        self,
        *,
        occupied: set[str] | None = None,
        health_failures: int = 0,
        verification: str = '{"policies":3,"projects":2,"files":1}',
    ) -> None:
        self.occupied = occupied or set()
        self.health_failures = health_failures
        self.verification = verification
        self.calls: list[tuple[tuple[str, ...], dict[str, str], bytes | None, int]] = []
        self.target_checks = 0

    def target_resources(self, project_name: str, environment: dict[str, str]) -> set[str]:
        self.target_checks += 1
        assert environment["DATABASE_URL"].endswith("@mysql:3306/policy")
        return self.occupied

    def run(
        self,
        arguments: tuple[str, ...],
        *,
        environment: dict[str, str],
        input_path: Path | None = None,
        timeout_seconds: int,
    ) -> str:
        self.calls.append((arguments, environment, input_path, timeout_seconds))
        if "recovery-health" in arguments[-1]:
            if self.health_failures:
                self.health_failures -= 1
                raise RecoveryRefused("recovery_restore_failed")
            return "ok"
        if "recovery-verification" in arguments[-1]:
            return self.verification
        return ""


def _entry(path: str, content: bytes) -> dict[str, object]:
    return {"path": path, "size": len(content), "sha256": hashlib.sha256(content).hexdigest()}


def _make_set(root: Path, *, archive_member: str = "captured/page.txt") -> str:
    backup_set = root / "sets" / "17-20260820T033000Z"
    backup_set.mkdir(parents=True)
    database = b"CREATE TABLE policies (id int);"
    (backup_set / "database.sql").write_bytes(database)
    archive_stream = io.BytesIO()
    with tarfile.open(fileobj=archive_stream, mode="w") as archive:
        info = tarfile.TarInfo(archive_member)
        info.size = len(b"page")
        archive.addfile(info, io.BytesIO(b"page"))
    archive_data = archive_stream.getvalue()
    (backup_set / "files.tar").write_bytes(archive_data)
    (backup_set / "manifest.json").write_text(
        json.dumps(
            {
                "format_version": 1,
                "completed_at": "2026-08-20T03:30:00+00:00",
                "files": [_entry("database.sql", database), _entry("files.tar", archive_data)],
            }
        ),
        encoding="utf-8",
    )
    return "sets/17-20260820T033000Z"


@pytest.mark.parametrize(
    ("set_path", "project_name", "code"),
    [
        ("../other", "stage5-recovery-1", "recovery_set_path_invalid"),
        ("sets/17-20260820T033000Z", "stage4-wecom-verify", "recovery_project_invalid"),
        ("sets/17-20260820T033000Z", "stage5-recovery-ACCEPTANCE", "recovery_project_invalid"),
    ],
)
def test_recovery_refuses_unsafe_root_or_project_name(
    tmp_path: Path, set_path: str, project_name: str, code: str
) -> None:
    _make_set(tmp_path)

    with pytest.raises(RecoveryRefused, match=code):
        build_recovery_plan(tmp_path, set_path, project_name)


def test_recovery_rejects_tampered_set_before_compose_runs(tmp_path: Path) -> None:
    set_path = _make_set(tmp_path)
    (tmp_path / set_path / "database.sql").write_bytes(b"X" * len(b"CREATE TABLE policies (id int);"))
    runner = FakeRunner()

    with pytest.raises(RecoveryRefused, match="manifest_checksum_invalid"):
        restore_backup(tmp_path, set_path, "stage5-recovery-1", runner)

    assert runner.calls == []


def test_recovery_rejects_unsafe_archive_before_compose_runs(tmp_path: Path) -> None:
    set_path = _make_set(tmp_path, archive_member="../outside.txt")
    runner = FakeRunner()

    with pytest.raises(RecoveryRefused, match="recovery_archive_member_invalid"):
        restore_backup(tmp_path, set_path, "stage5-recovery-1", runner)

    assert runner.calls == []


def test_recovery_rejects_existing_target_resources_before_restore(tmp_path: Path) -> None:
    set_path = _make_set(tmp_path)
    runner = FakeRunner(occupied={"stage5-recovery-1-mysql-data"})

    with pytest.raises(RecoveryRefused, match="recovery_target_in_use"):
        restore_backup(tmp_path, set_path, "stage5-recovery-1", runner)

    assert runner.calls == []


def test_recovery_environment_ignores_acceptance_database_url_and_webhook() -> None:
    environment = build_recovery_environment(
        {
            "DATABASE_URL": "mysql+pymysql://acceptance-user:acceptance-password@acceptance-db:3306/live",
            "WECOM_WEBHOOK_URL": "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=acceptance",
            "DEEPSEEK_API_KEY": "acceptance-ai-key",
        }
    )

    assert environment["DATABASE_URL"].endswith("@mysql:3306/policy")
    assert "acceptance-db" not in " ".join(environment.values())
    assert "acceptance" not in " ".join(environment.values())
    assert environment["WECOM_WEBHOOK_URL"] == ""
    assert environment["DEEPSEEK_API_KEY"] == ""
    assert environment["AI_ADAPTER"] == "mock"


def test_recovery_refuses_nondefault_docker_target_before_preflight(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DOCKER_HOST", "tcp://acceptance-docker:2376")
    runner = FakeRunner()

    with pytest.raises(RecoveryRefused, match="recovery_docker_target_invalid"):
        restore_backup(tmp_path, _make_set(tmp_path), "stage5-recovery-1", runner)

    assert runner.target_checks == 0
    assert runner.calls == []


def test_recovery_runs_fixed_isolated_commands_and_returns_safe_report(tmp_path: Path) -> None:
    set_path = _make_set(tmp_path)
    runner = FakeRunner()
    before = datetime(2026, 8, 20, 4, 0, tzinfo=UTC)
    after = datetime(2026, 8, 20, 4, 1, tzinfo=UTC)
    clock = iter((before, after))

    report = restore_backup(
        tmp_path,
        set_path,
        "stage5-recovery-1",
        runner,
        now_factory=lambda: next(clock),
    )

    assert report.backup_job_id == 17
    assert (report.policy_count, report.project_count, report.file_count) == (3, 2, 1)
    assert report.status == "succeeded"
    assert report.started_at == before
    assert report.completed_at == after
    calls = [call[0] for call in runner.calls]
    assert calls[0][-3:] == ("up", "-d", "mysql")
    assert calls[1][-3:] == ("-e", "SELECT 1", "policy")
    assert calls[2][-3:] == ("mysql", "-uroot", "policy")
    assert calls[3][-5:] == ("restore-files", "cp", "-a", "/input/.", "/runtime/files/")
    assert any(argument.endswith(":/input:ro") for argument in calls[3])
    assert "api:/runtime/files/" not in calls[3]
    assert calls[4][-3:] == ("up", "-d", "api")
    assert "recovery-health" in calls[5][-1]
    assert "recovery-verification" in calls[6][-1]
    assert all(isinstance(call, tuple) for call in calls)
    for _, environment, _, _ in runner.calls:
        serialized_environment = json.dumps(environment)
        assert "acceptance-db" not in serialized_environment
        assert "qyapi.weixin" not in serialized_environment
    safe = json.dumps(report.as_dict())
    for forbidden in (str(tmp_path), "CREATE TABLE", "MYSQL_PWD", "password", "webhook"):
        assert forbidden not in safe


def test_recovery_readiness_requires_authenticated_database_query(tmp_path: Path) -> None:
    runner = FakeRunner()

    restore_backup(tmp_path, _make_set(tmp_path), "stage5-recovery-1", runner)

    readiness_command, readiness_environment, _, _ = runner.calls[1]
    assert readiness_command[-11:] == (
        "exec", "-T", "-e", "MYSQL_PWD", "mysql", "mysql",
        "-uroot", "-N", "-e", "SELECT 1", "policy",
    )
    assert readiness_environment["MYSQL_PWD"] == readiness_environment["MYSQL_ROOT_PASSWORD"]


def test_recovery_import_does_not_load_entire_sql_dump_into_memory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_path = _make_set(tmp_path)
    runner = FakeRunner()
    original_read_bytes = Path.read_bytes

    def reject_dump_buffering(path: Path) -> bytes:
        if path.name == "database.sql":
            raise AssertionError("SQL dump must be streamed")
        return original_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", reject_dump_buffering)

    restore_backup(tmp_path, set_path, "stage5-recovery-1", runner)

    assert runner.calls[2][2] is not None
    assert runner.calls[2][2].name == "database.sql"


def test_recovery_rejects_set_changed_after_preflight_before_docker(tmp_path: Path) -> None:
    set_path = _make_set(tmp_path)

    class MutatingRunner(FakeRunner):
        def target_resources(self, project_name: str, environment: dict[str, str]) -> set[str]:
            (tmp_path / set_path / "database.sql").write_bytes(
                b"X" * len(b"CREATE TABLE policies (id int);")
            )
            return super().target_resources(project_name, environment)

    runner = MutatingRunner()

    with pytest.raises(RecoveryRefused, match="manifest_checksum_invalid"):
        restore_backup(tmp_path, set_path, "stage5-recovery-1", runner)

    assert runner.calls == []


def test_recovery_polls_health_before_verification(tmp_path: Path) -> None:
    set_path = _make_set(tmp_path)
    runner = FakeRunner(health_failures=2)

    restore_backup(tmp_path, set_path, "stage5-recovery-1", runner)

    calls = [call[0] for call in runner.calls]
    health_indexes = [index for index, call in enumerate(calls) if "recovery-health" in call[-1]]
    assert health_indexes == [5, 6, 7]
    assert "recovery-verification" in calls[8][-1]


def test_recovery_health_poll_has_a_wall_clock_timeout(tmp_path: Path) -> None:
    clock = iter((0.0, 0.0, 61.0))

    with pytest.raises(RecoveryRefused, match="recovery_health_timeout"):
        restore_backup(
            tmp_path,
            _make_set(tmp_path),
            "stage5-recovery-1",
            FakeRunner(health_failures=10),
            sleep=lambda _: None,
            monotonic=lambda: next(clock),
        )


def test_recovery_refuses_file_count_mismatch(tmp_path: Path) -> None:
    set_path = _make_set(tmp_path)
    runner = FakeRunner(verification='{"policies":3,"projects":2,"files":0}')

    with pytest.raises(RecoveryRefused, match="recovery_file_count_mismatch"):
        restore_backup(tmp_path, set_path, "stage5-recovery-1", runner)


def test_cli_returns_only_safe_json_for_unexpected_operational_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def fail(*_: object, **__: object) -> object:
        raise PermissionError(f"cannot read {tmp_path} with acceptance-password")

    monkeypatch.setattr("scripts.recover_backup.restore_backup", fail)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "recover_backup",
            "--backup-root",
            str(tmp_path),
            "--set",
            "sets/17-20260820T033000Z",
            "--project-name",
            "stage5-recovery-1",
        ],
    )

    assert main() == 1
    assert capsys.readouterr().out == '{"status":"failed","summary":"recovery_operation_failed"}\n'


def test_default_collision_preflight_checks_project_networks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.recover_backup import DockerRecoveryRunner

    commands: list[tuple[str, ...]] = []

    def list_resources(command: tuple[str, ...], **_: object) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        output = "stage5-recovery-1-default\n" if command[1:3] == ("network", "ls") else ""
        return subprocess.CompletedProcess(command, 0, stdout=output, stderr="")

    monkeypatch.setattr("scripts.recover_backup.subprocess.run", list_resources)

    resources = DockerRecoveryRunner().target_resources(
        "stage5-recovery-1", build_recovery_environment()
    )

    assert resources == {"stage5-recovery-1-default"}
    assert ("docker", "network", "ls", "--format", "{{.Name}}") in commands


def test_docker_runner_sets_a_timeout_on_every_subprocess(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.recover_backup import (
        DISCOVERY_TIMEOUT_SECONDS,
        DockerRecoveryRunner,
        SQL_IMPORT_TIMEOUT_SECONDS,
    )

    timeouts: list[object] = []

    def completed(command: tuple[str, ...], **kwargs: object) -> subprocess.CompletedProcess[bytes]:
        timeouts.append(kwargs.get("timeout"))
        return subprocess.CompletedProcess(command, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr("scripts.recover_backup.subprocess.run", completed)
    runner = DockerRecoveryRunner()
    environment = build_recovery_environment()
    runner.target_resources("stage5-recovery-1", environment)
    runner.run(
        ("docker", "version"), environment=environment, timeout_seconds=SQL_IMPORT_TIMEOUT_SECONDS
    )

    assert timeouts == [DISCOVERY_TIMEOUT_SECONDS] * 3 + [SQL_IMPORT_TIMEOUT_SECONDS]


def test_recovery_assigns_longer_finite_timeouts_to_restore_operations(tmp_path: Path) -> None:
    from scripts.recover_backup import (
        COMPOSE_OPERATION_TIMEOUT_SECONDS,
        FILE_RESTORE_TIMEOUT_SECONDS,
        READINESS_PROBE_TIMEOUT_SECONDS,
        SQL_IMPORT_TIMEOUT_SECONDS,
        VERIFICATION_TIMEOUT_SECONDS,
    )

    runner = FakeRunner()
    restore_backup(tmp_path, _make_set(tmp_path), "stage5-recovery-1", runner)

    assert [call[3] for call in runner.calls] == [
        COMPOSE_OPERATION_TIMEOUT_SECONDS,
        READINESS_PROBE_TIMEOUT_SECONDS,
        SQL_IMPORT_TIMEOUT_SECONDS,
        FILE_RESTORE_TIMEOUT_SECONDS,
        COMPOSE_OPERATION_TIMEOUT_SECONDS,
        READINESS_PROBE_TIMEOUT_SECONDS,
        VERIFICATION_TIMEOUT_SECONDS,
    ]
    assert READINESS_PROBE_TIMEOUT_SECONDS < SQL_IMPORT_TIMEOUT_SECONDS
    assert READINESS_PROBE_TIMEOUT_SECONDS < FILE_RESTORE_TIMEOUT_SECONDS


def test_docker_runner_preserves_only_docker_client_home_paths(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.recover_backup import DockerRecoveryRunner

    monkeypatch.setenv("HOME", "C:/operator-home")
    monkeypatch.setenv("USERPROFILE", "C:/operator-profile")

    environment = DockerRecoveryRunner._process_environment(build_recovery_environment())

    assert environment["HOME"] == "C:/operator-home"
    assert environment["USERPROFILE"] == "C:/operator-profile"


def test_docker_runner_converts_a_stalled_subprocess_to_a_safe_timeout(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from scripts.recover_backup import DockerRecoveryRunner

    def stalled(command: tuple[str, ...], **_: object) -> object:
        raise subprocess.TimeoutExpired(command, 30)

    monkeypatch.setattr("scripts.recover_backup.subprocess.run", stalled)

    with pytest.raises(RecoveryRefused, match="recovery_docker_timeout"):
        DockerRecoveryRunner().run(
            ("docker", "version"),
            environment=build_recovery_environment(),
            timeout_seconds=10,
        )


def test_docker_runner_streams_sql_from_file_handle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from scripts.recover_backup import DockerRecoveryRunner

    dump = tmp_path / "database.sql"
    dump.write_bytes(b"CREATE TABLE test (id int);")
    observed = {"streamed": False}

    def inspect_subprocess(_arguments: tuple[str, ...], **kwargs: object) -> object:
        assert "input" not in kwargs
        stream = kwargs["stdin"]
        assert stream is not None
        assert stream.read() == b"CREATE TABLE test (id int);"
        observed["streamed"] = True
        return SimpleNamespace(returncode=0, stdout=b"")

    monkeypatch.setattr("scripts.recover_backup.subprocess.run", inspect_subprocess)

    DockerRecoveryRunner().run(
        ("docker", "compose", "exec"),
        environment=build_recovery_environment(),
        input_path=dump,
        timeout_seconds=10,
    )

    assert observed["streamed"] is True


def test_recovery_compose_has_internal_network_and_pinned_offline_restore_helper() -> None:
    compose = (Path(__file__).parents[4] / "compose.recovery.yaml").read_text(encoding="utf-8")

    assert "env_file:" not in compose
    assert "internal: true" in compose
    assert "network_mode: none" in compose
    assert re.search(r"image: alpine@sha256:[0-9a-f]{64}", compose)
    assert "- recovery-files:/runtime/files" in compose


def test_runner_failure_has_only_a_stable_safe_code(tmp_path: Path) -> None:
    class FailingRunner(FakeRunner):
        def run(
            self,
            arguments: tuple[str, ...],
            *,
            environment: dict[str, str],
            input_path: Path | None = None,
            timeout_seconds: int,
        ) -> str:
            raise RuntimeError("acceptance-password at C:/unsafe")

    with pytest.raises(RecoveryRefused, match="recovery_restore_failed") as error:
        restore_backup(tmp_path, _make_set(tmp_path), "stage5-recovery-1", FailingRunner())

    assert "acceptance-password" not in str(error.value)
