"""Restore one verified backup set into an isolated Compose project."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from contextlib import ExitStack
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import secrets
import shutil
import subprocess
import tarfile
import tempfile
import time
from typing import Protocol
from urllib.parse import quote

from app.modules.backups.artifacts import BackupManifest, BackupSetValidationError, validate_backup_set


PROJECT_PATTERN = "stage5-recovery-"
HEALTHCHECK_SCRIPT = (
    "import json,sys,urllib.request;marker='recovery-health';"
    "response=json.loads(urllib.request.urlopen('http://127.0.0.1:8000/api/health',timeout=5).read());"
    "sys.exit(0 if response.get('status')=='ok' else 1)"
)
VERIFICATION_SCRIPT = (
    "import json;marker='recovery-verification';"
    "from pathlib import Path;"
    "from app.db.session import SessionLocal;"
    "from app.modules.policies.models import Policy;"
    "from app.modules.projects.models import Project;"
    "db=SessionLocal();"
    "result={'policies':db.query(Policy).count(),'projects':db.query(Project).count(),"
    "'files':sum(1 for p in Path('/runtime/files').rglob('*') if p.is_file())};"
    "db.close();print(json.dumps(result,separators=(',',':')))"
)
MAX_READY_ATTEMPTS = 10
READY_TIMEOUT_SECONDS = 60
DISCOVERY_TIMEOUT_SECONDS = 10
READINESS_PROBE_TIMEOUT_SECONDS = 5
COMPOSE_OPERATION_TIMEOUT_SECONDS = 300
SQL_IMPORT_TIMEOUT_SECONDS = 300
FILE_RESTORE_TIMEOUT_SECONDS = 180
VERIFICATION_TIMEOUT_SECONDS = 60
DOCKER_TARGET_VARIABLES = (
    "DOCKER_API_VERSION",
    "DOCKER_CERT_PATH",
    "DOCKER_CONFIG",
    "DOCKER_CONTEXT",
    "DOCKER_HOST",
    "DOCKER_TLS",
    "DOCKER_TLS_VERIFY",
)


class RecoveryRefused(Exception):
    """A stable safe reason why recovery cannot proceed."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class RecoveryPlan:
    project_name: str
    backup_job_id: int
    manifest: BackupManifest
    set_dir: Path
    archive_file_count: int


@dataclass(frozen=True)
class RecoveryReport:
    backup_job_id: int
    policy_count: int
    project_count: int
    file_count: int
    started_at: datetime
    completed_at: datetime
    status: str
    summary: str

    def as_dict(self) -> dict[str, object]:
        return {
            "backup_job_id": self.backup_job_id,
            "policy_count": self.policy_count,
            "project_count": self.project_count,
            "file_count": self.file_count,
            "started_at": self.started_at.astimezone(UTC).isoformat(),
            "completed_at": self.completed_at.astimezone(UTC).isoformat(),
            "status": self.status,
            "summary": self.summary,
        }


class RecoveryRunner(Protocol):
    def target_resources(self, project_name: str, environment: dict[str, str]) -> set[str]: ...

    def run(
        self,
        arguments: tuple[str, ...],
        *,
        environment: dict[str, str],
        input_path: Path | None = None,
        timeout_seconds: int,
    ) -> str: ...


def build_recovery_environment(source: Mapping[str, str] | None = None) -> dict[str, str]:
    """Create the only configuration that can reach the recovery Compose project."""

    del source
    database_name = "policy"
    database_user = "recovery"
    database_password = secrets.token_urlsafe(32)
    return {
        "APP_ENV": "recovery",
        "AI_ADAPTER": "mock",
        "COMPOSE_PROJECT_NAME": "",
        "DATABASE_URL": (
            f"mysql+pymysql://{database_user}:{quote(database_password, safe='')}@mysql:3306/{database_name}"
        ),
        "DEEPSEEK_API_KEY": "",
        "FILE_STORAGE_ROOT": "/runtime/files",
        "JWT_SECRET": secrets.token_urlsafe(32),
        "MYSQL_DATABASE": database_name,
        "MYSQL_PASSWORD": database_password,
        "MYSQL_PWD": "",
        "MYSQL_ROOT_PASSWORD": secrets.token_urlsafe(32),
        "MYSQL_USER": database_user,
        "PUBLIC_BASE_URL": "",
        "WECOM_WEBHOOK_URL": "",
    }


def _require_default_docker_target(source: Mapping[str, str]) -> None:
    if any(source.get(variable) for variable in DOCKER_TARGET_VARIABLES):
        raise RecoveryRefused("recovery_docker_target_invalid")


def _portable_relative(value: str) -> PurePosixPath:
    if (
        not value
        or "\\" in value
        or ":" in value
        or Path(value).is_absolute()
        or PureWindowsPath(value).is_absolute()
        or PureWindowsPath(value).drive
    ):
        raise RecoveryRefused("recovery_set_path_invalid")
    relative = PurePosixPath(value)
    if relative.is_absolute() or ".." in relative.parts or relative == PurePosixPath("."):
        raise RecoveryRefused("recovery_set_path_invalid")
    return relative


def _inside(root: Path, relative: str) -> Path:
    portable = _portable_relative(relative)
    resolved_root = root.resolve()
    if not resolved_root.is_dir():
        raise RecoveryRefused("recovery_root_invalid")
    candidate = resolved_root
    for part in portable.parts:
        candidate = candidate / part
        if candidate.is_symlink():
            raise RecoveryRefused("recovery_set_path_invalid")
    resolved_candidate = candidate.resolve()
    if resolved_candidate == resolved_root or resolved_root not in resolved_candidate.parents:
        raise RecoveryRefused("recovery_set_path_invalid")
    return resolved_candidate


def _backup_job_id(relative_set_path: str) -> int:
    name = _portable_relative(relative_set_path).name
    first, separator, _ = name.partition("-")
    if not separator or not first.isdigit() or int(first) < 1:
        raise RecoveryRefused("recovery_backup_id_invalid")
    return int(first)


def _safe_member_path(name: str) -> PurePosixPath:
    if not name or "\\" in name or ":" in name:
        raise RecoveryRefused("recovery_archive_member_invalid")
    member_path = PurePosixPath(name)
    if member_path.is_absolute() or ".." in member_path.parts or member_path == PurePosixPath("."):
        raise RecoveryRefused("recovery_archive_member_invalid")
    return member_path


def _validate_archive_members(archive_path: Path) -> int:
    try:
        with tarfile.open(archive_path, mode="r:*") as archive:
            seen: set[PurePosixPath] = set()
            for member in archive.getmembers():
                member_path = _safe_member_path(member.name)
                if not member.isfile() or member_path in seen:
                    raise RecoveryRefused("recovery_archive_member_invalid")
                seen.add(member_path)
            return len(seen)
    except RecoveryRefused:
        raise
    except (OSError, tarfile.TarError):
        raise RecoveryRefused("recovery_archive_invalid") from None


def _valid_project_name(project_name: str) -> bool:
    suffix = project_name.removeprefix(PROJECT_PATTERN)
    return (
        project_name.startswith(PROJECT_PATTERN)
        and bool(suffix)
        and all(character.isdigit() or "a" <= character <= "z" or character == "-" for character in suffix)
        and project_name not in {"stage4-wecom-verify", os.environ.get("COMPOSE_PROJECT_NAME", "")}
    )


def build_recovery_plan(root: Path, set_path: str, project_name: str) -> RecoveryPlan:
    """Perform every filesystem and manifest refusal before Docker is used."""

    if not _valid_project_name(project_name):
        raise RecoveryRefused("recovery_project_invalid")
    try:
        set_dir = _inside(Path(root), set_path)
        manifest = validate_backup_set(Path(root), set_path)
        archive_file_count = _validate_archive_members(set_dir / "files.tar")
        backup_job_id = _backup_job_id(set_path)
    except RecoveryRefused:
        raise
    except BackupSetValidationError as error:
        raise RecoveryRefused(error.code) from None
    except Exception:
        raise RecoveryRefused("recovery_preflight_failed") from None
    return RecoveryPlan(
        project_name=project_name,
        backup_job_id=backup_job_id,
        manifest=manifest,
        set_dir=set_dir,
        archive_file_count=archive_file_count,
    )


def _extract_archive(plan: RecoveryPlan, target: Path) -> None:
    try:
        with tarfile.open(plan.set_dir / "files.tar", mode="r:*") as archive:
            members = archive.getmembers()
            for member in members:
                _safe_member_path(member.name)
                if not member.isfile():
                    raise RecoveryRefused("recovery_archive_member_invalid")
            archive.extractall(target, members=members, filter="data")
    except RecoveryRefused:
        raise
    except (OSError, tarfile.TarError):
        raise RecoveryRefused("recovery_archive_invalid") from None


def _compose_prefix(project_name: str) -> tuple[str, ...]:
    compose_file = Path(__file__).resolve().parents[2] / "compose.recovery.yaml"
    return ("docker", "compose", "-p", project_name, "-f", str(compose_file))


def _verification_counts(raw: str) -> tuple[int, int, int]:
    try:
        result = json.loads(raw)
        if not isinstance(result, dict) or any(
            not isinstance(result.get(name), int) or result[name] < 0
            for name in ("policies", "projects", "files")
        ):
            raise ValueError
        return result["policies"], result["projects"], result["files"]
    except (TypeError, ValueError, json.JSONDecodeError):
        raise RecoveryRefused("recovery_verification_failed") from None


def _wait_for_ready(
    runner: RecoveryRunner,
    command: tuple[str, ...],
    environment: dict[str, str],
    failure_code: str,
    sleep: Callable[[float], None],
    monotonic: Callable[[], float],
) -> None:
    deadline = monotonic() + READY_TIMEOUT_SECONDS
    for attempt in range(MAX_READY_ATTEMPTS):
        try:
            runner.run(
                command,
                environment=environment,
                timeout_seconds=READINESS_PROBE_TIMEOUT_SECONDS,
            )
            return
        except RecoveryRefused:
            current_time = monotonic()
            if attempt == MAX_READY_ATTEMPTS - 1 or current_time >= deadline:
                break
            sleep(min(1, max(0, deadline - current_time)))
    raise RecoveryRefused(failure_code)


def restore_backup(
    root: Path,
    set_path: str,
    project_name: str,
    runner: RecoveryRunner,
    *,
    now_factory: Callable[[], datetime] = lambda: datetime.now(UTC),
    sleep: Callable[[float], None] = time.sleep,
    monotonic: Callable[[], float] = time.monotonic,
) -> RecoveryReport:
    """Run the isolated drill without emitting paths, output, credentials, or restored data."""

    try:
        _require_default_docker_target(os.environ)
        plan = build_recovery_plan(root, set_path, project_name)
        environment = build_recovery_environment()
        environment["COMPOSE_PROJECT_NAME"] = plan.project_name
        environment["MYSQL_PWD"] = environment["MYSQL_ROOT_PASSWORD"]
    except RecoveryRefused:
        raise
    except Exception:
        raise RecoveryRefused("recovery_preflight_failed") from None
    try:
        if runner.target_resources(plan.project_name, environment):
            raise RecoveryRefused("recovery_target_in_use")
    except RecoveryRefused:
        raise
    except Exception:
        raise RecoveryRefused("recovery_preflight_failed") from None

    started_at = now_factory()
    prefix = _compose_prefix(plan.project_name)
    try:
        with tempfile.TemporaryDirectory(prefix="stage5-recovery-") as temporary:
            extraction_root = Path(temporary)
            snapshot_set = extraction_root.joinpath(*PurePosixPath(set_path).parts)
            snapshot_set.mkdir(parents=True)
            for name in ("manifest.json", "database.sql", "files.tar"):
                shutil.copyfile(plan.set_dir / name, snapshot_set / name)
            snapshot_plan = build_recovery_plan(extraction_root, set_path, project_name)
            if (
                snapshot_plan.manifest != plan.manifest
                or snapshot_plan.archive_file_count != plan.archive_file_count
            ):
                raise RecoveryRefused("recovery_set_changed")
            file_input_root = extraction_root / "files"
            file_input_root.mkdir()
            _extract_archive(snapshot_plan, file_input_root)
            runner.run(
                prefix + ("up", "-d", "mysql"),
                environment=environment,
                timeout_seconds=COMPOSE_OPERATION_TIMEOUT_SECONDS,
            )
            _wait_for_ready(
                runner,
                prefix
                + (
                    "exec", "-T", "-e", "MYSQL_PWD", "mysql", "mysql",
                    "-uroot", "-N", "-e", "SELECT 1", environment["MYSQL_DATABASE"],
                ),
                environment,
                "recovery_mysql_timeout",
                sleep,
                monotonic,
            )
            runner.run(
                prefix
                + (
                    "exec",
                    "-T",
                    "-e",
                    "MYSQL_PWD",
                    "mysql",
                    "mysql",
                    "-uroot",
                    environment["MYSQL_DATABASE"],
                ),
                environment=environment,
                input_path=snapshot_plan.set_dir / "database.sql",
                timeout_seconds=SQL_IMPORT_TIMEOUT_SECONDS,
            )
            runner.run(
                prefix
                + (
                    "run",
                    "--rm",
                    "--no-deps",
                    "-T",
                    "-v",
                    f"{file_input_root}:/input:ro",
                    "restore-files",
                    "cp",
                    "-a",
                    "/input/.",
                    "/runtime/files/",
                ),
                environment=environment,
                timeout_seconds=FILE_RESTORE_TIMEOUT_SECONDS,
            )
            runner.run(
                prefix + ("up", "-d", "api"),
                environment=environment,
                timeout_seconds=COMPOSE_OPERATION_TIMEOUT_SECONDS,
            )
            _wait_for_ready(
                runner,
                prefix + ("exec", "-T", "api", "python", "-c", HEALTHCHECK_SCRIPT),
                environment,
                "recovery_health_timeout",
                sleep,
                monotonic,
            )
            verification = runner.run(
                prefix + ("exec", "-T", "api", "python", "-c", VERIFICATION_SCRIPT),
                environment=environment,
                timeout_seconds=VERIFICATION_TIMEOUT_SECONDS,
            )
        policy_count, project_count, file_count = _verification_counts(verification)
        if file_count != plan.archive_file_count:
            raise RecoveryRefused("recovery_file_count_mismatch")
    except RecoveryRefused:
        raise
    except Exception:
        raise RecoveryRefused("recovery_restore_failed") from None
    completed_at = now_factory()
    return RecoveryReport(
        backup_job_id=plan.backup_job_id,
        policy_count=policy_count,
        project_count=project_count,
        file_count=file_count,
        started_at=started_at,
        completed_at=completed_at,
        status="succeeded",
        summary="Recovery drill completed.",
    )


class DockerRecoveryRunner:
    """Default runner that suppresses all Docker output and never uses a shell."""

    _SYSTEM_ENVIRONMENT_KEYS = (
        "APPDATA",
        "COMSPEC",
        "HOME",
        "LOCALAPPDATA",
        "PATH",
        "SystemRoot",
        "TEMP",
        "TMP",
        "USERPROFILE",
        "WINDIR",
    )

    @classmethod
    def _process_environment(cls, recovery_environment: Mapping[str, str]) -> dict[str, str]:
        environment = {
            key: os.environ[key] for key in cls._SYSTEM_ENVIRONMENT_KEYS if key in os.environ
        }
        environment.update(recovery_environment)
        return environment

    def target_resources(self, project_name: str, environment: dict[str, str]) -> set[str]:
        resources: set[str] = set()
        label_filter = f"label=com.docker.compose.project={project_name}"
        for command, label_scoped in (
            (("docker", "ps", "-a", "--format", "{{.Names}}"), False),
            (("docker", "ps", "-a", "--filter", label_filter, "--format", "{{.Names}}"), True),
            (("docker", "volume", "ls", "--format", "{{.Name}}"), False),
            (("docker", "volume", "ls", "--filter", label_filter, "--format", "{{.Name}}"), True),
            (("docker", "network", "ls", "--format", "{{.Name}}"), False),
            (("docker", "network", "ls", "--filter", label_filter, "--format", "{{.Name}}"), True),
        ):
            try:
                result = subprocess.run(
                    command,
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=DISCOVERY_TIMEOUT_SECONDS,
                    env=self._process_environment(environment),
                )
            except subprocess.TimeoutExpired:
                raise RecoveryRefused("recovery_docker_timeout") from None
            if result.returncode != 0:
                raise RecoveryRefused("recovery_docker_unavailable")
            if label_scoped:
                resources.update(result.stdout.splitlines())
            else:
                resources.update(
                    item
                    for item in result.stdout.splitlines()
                    if item.startswith((project_name + "-", project_name + "_"))
                )
        return resources

    def run(
        self,
        arguments: tuple[str, ...],
        *,
        environment: dict[str, str],
        input_path: Path | None = None,
        timeout_seconds: int,
    ) -> str:
        try:
            with ExitStack() as stack:
                input_stream = stack.enter_context(input_path.open("rb")) if input_path else None
                result = subprocess.run(
                    arguments,
                    check=False,
                    stdin=input_stream,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    timeout=timeout_seconds,
                    env=self._process_environment(environment),
                )
        except subprocess.TimeoutExpired:
            raise RecoveryRefused("recovery_docker_timeout") from None
        if result.returncode != 0:
            raise RecoveryRefused("recovery_restore_failed")
        return result.stdout.decode("utf-8", errors="replace")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run an isolated Stage 5 recovery drill.")
    parser.add_argument("--backup-root", required=True)
    parser.add_argument("--set", required=True)
    parser.add_argument("--project-name", required=True)
    arguments = parser.parse_args()
    try:
        report = restore_backup(
            Path(arguments.backup_root),
            arguments.set,
            arguments.project_name,
            DockerRecoveryRunner(),
        )
    except RecoveryRefused as error:
        print(json.dumps({"status": "failed", "summary": error.code}, separators=(",", ":")))
        return 1
    except Exception:
        print(json.dumps({"status": "failed", "summary": "recovery_operation_failed"}, separators=(",", ":")))
        return 1
    print(json.dumps(report.as_dict(), separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
