"""Safe creation and validation of portable backup artifact sets."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import subprocess
import tarfile
import time
from typing import Any, cast
from uuid import uuid4

from sqlalchemy.engine import make_url

from app.core.config import Settings


BACKUP_FORMAT_VERSION = 1


class BackupSetValidationError(Exception):
    """A completed backup set does not meet the portable manifest contract."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


class BackupArtifactError(Exception):
    """A safe failure returned to the backup worker."""

    def __init__(self, code: str, summary: str) -> None:
        self.code = code
        self.summary = summary
        super().__init__(code)


@dataclass(frozen=True)
class BackupManifestFile:
    path: str
    size: int
    sha256: str


@dataclass(frozen=True)
class BackupManifest:
    format_version: int
    completed_at: datetime
    files: dict[str, BackupManifestFile]


@dataclass(frozen=True)
class BackupArtifactResult:
    relative_set_path: str
    manifest_sha256: str
    dump_bytes: int
    archive_bytes: int
    total_bytes: int
    completed_at: datetime


DumpRunner = Callable[[Path], None]
ProcessRunner = Callable[..., Any]


def _stable_error(code: str, summary: str) -> BackupArtifactError:
    return BackupArtifactError(code, summary)


def _portable_relative(relative: str) -> PurePosixPath:
    if (
        not relative
        or "\\" in relative
        or ":" in relative
        or Path(relative).is_absolute()
        or PureWindowsPath(relative).is_absolute()
        or PureWindowsPath(relative).drive
    ):
        raise BackupSetValidationError("manifest_path_invalid")
    candidate = PurePosixPath(relative)
    if candidate.is_absolute() or ".." in candidate.parts or candidate == PurePosixPath("."):
        raise BackupSetValidationError("manifest_path_invalid")
    return candidate


def _inside(root: Path, relative: str) -> Path:
    portable = _portable_relative(relative)
    unresolved_candidate = root / Path(*portable.parts)
    component = root
    for part in portable.parts:
        component = component / part
        if component.is_symlink():
            raise BackupSetValidationError("manifest_path_invalid")
    resolved_root = root.resolve()
    candidate = unresolved_candidate.resolve()
    if candidate == resolved_root or resolved_root not in candidate.parents:
        raise BackupSetValidationError("manifest_path_invalid")
    return candidate


def _sha256_and_size(path: Path, ensure_time: Callable[[], object] | None = None) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            if ensure_time is not None:
                ensure_time()
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _fsync_file(path: Path) -> None:
    with path.open("r+b") as stream:
        os.fsync(stream.fileno())


def _fsync_directory(path: Path) -> None:
    try:
        descriptor = os.open(path, getattr(os, "O_DIRECTORY", 0))
    except OSError:
        return
    try:
        os.fsync(descriptor)
    except OSError:
        pass
    finally:
        os.close(descriptor)


def _manifest_file(entry: object) -> BackupManifestFile:
    if not isinstance(entry, dict):
        raise BackupSetValidationError("manifest_invalid")
    path = entry.get("path")
    size = entry.get("size")
    sha256 = entry.get("sha256")
    if not isinstance(path, str) or not isinstance(size, int) or size < 0:
        raise BackupSetValidationError("manifest_invalid")
    if not isinstance(sha256, str) or len(sha256) != 64:
        raise BackupSetValidationError("manifest_invalid")
    try:
        int(sha256, 16)
    except ValueError:
        raise BackupSetValidationError("manifest_invalid") from None
    _portable_relative(path)
    return BackupManifestFile(path=path, size=size, sha256=sha256)


def validate_backup_set(
    root: Path, relative_set_path: str, *, ensure_time: Callable[[], object] | None = None
) -> BackupManifest:
    """Validate a completed set without exposing local paths or contents."""

    backup_set = _inside(root, relative_set_path)
    if backup_set.is_symlink() or not backup_set.is_dir():
        raise BackupSetValidationError("manifest_set_missing")
    manifest_path = backup_set / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise BackupSetValidationError("manifest_missing")
    try:
        raw_manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise BackupSetValidationError("manifest_invalid") from None
    if not isinstance(raw_manifest, dict):
        raise BackupSetValidationError("manifest_invalid")
    if raw_manifest.get("format_version") != BACKUP_FORMAT_VERSION:
        raise BackupSetValidationError("manifest_version_unsupported")
    raw_completed_at = raw_manifest.get("completed_at")
    if not isinstance(raw_completed_at, str):
        raise BackupSetValidationError("manifest_invalid")
    try:
        completed_at = datetime.fromisoformat(raw_completed_at.replace("Z", "+00:00"))
    except ValueError:
        raise BackupSetValidationError("manifest_invalid") from None
    if completed_at.tzinfo is None:
        raise BackupSetValidationError("manifest_invalid")
    raw_files = raw_manifest.get("files")
    if not isinstance(raw_files, list):
        raise BackupSetValidationError("manifest_invalid")
    files: dict[str, BackupManifestFile] = {}
    for raw_entry in raw_files:
        entry = _manifest_file(raw_entry)
        if entry.path in files:
            raise BackupSetValidationError("manifest_duplicate_path")
        files[entry.path] = entry
    if set(files) != {"database.sql", "files.tar"}:
        raise BackupSetValidationError("manifest_required_files_missing")
    for entry in files.values():
        file_path = _inside(backup_set, entry.path)
        if file_path.is_symlink() or not file_path.is_file():
            raise BackupSetValidationError("manifest_file_missing")
        digest, size = _sha256_and_size(file_path, ensure_time)
        if size != entry.size:
            raise BackupSetValidationError("manifest_size_invalid")
        if digest != entry.sha256:
            raise BackupSetValidationError("manifest_checksum_invalid")
    try:
        on_disk_names = {entry.name for entry in backup_set.iterdir()}
    except OSError:
        raise BackupSetValidationError("manifest_invalid") from None
    if on_disk_names != {"manifest.json", "database.sql", "files.tar"}:
        raise BackupSetValidationError("manifest_unexpected_entry")
    return BackupManifest(
        format_version=BACKUP_FORMAT_VERSION,
        completed_at=completed_at.astimezone(timezone.utc),
        files=files,
    )


class _DeadlineReader(io.BufferedReader):
    def __init__(self, raw: io.RawIOBase, ensure_time: Callable[[], object]) -> None:
        super().__init__(raw)
        self._ensure_time = ensure_time

    def read(self, size: int | None = -1) -> bytes:
        self._ensure_time()
        content = super().read(size)
        self._ensure_time()
        return content


class BackupArtifactWriter:
    """Create an atomically promoted set below the configured backup root."""

    def __init__(
        self,
        root: Path,
        *,
        database_url: str | None = None,
        dump_runner: DumpRunner | None = None,
        file_root: Path | None = None,
        process_runner: ProcessRunner = subprocess.run,
        timeout_seconds: int = 1800,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.root = Path(root)
        self.database_url = database_url
        self.dump_runner = dump_runner
        self.file_root = Path(file_root) if file_root is not None else None
        self.process_runner = process_runner
        self.timeout_seconds = timeout_seconds
        self.clock = clock

    @classmethod
    def from_settings(
        cls,
        settings: Settings,
        *,
        dump_runner: DumpRunner | None = None,
        process_runner: ProcessRunner = subprocess.run,
    ) -> BackupArtifactWriter:
        return cls(
            Path(settings.backup_root),
            database_url=settings.database_url,
            dump_runner=dump_runner,
            file_root=Path(settings.file_storage_root),
            process_runner=process_runner,
            timeout_seconds=max(1, settings.backup_job_timeout_seconds - 5),
        )

    def create(self, job_id: int) -> BackupArtifactResult:
        if job_id < 1:
            raise _stable_error("backup_job_invalid", "Backup job is invalid.")
        temporary: Path | None = None
        promoted: Path | None = None
        deadline = self.clock() + self.timeout_seconds
        try:
            self.root.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.root.chmod(0o700)
            temporary = self.root / f".tmp-{job_id}-{uuid4().hex}"
            temporary.mkdir(mode=0o700)
            database_path = temporary / "database.sql"
            self._write_dump(database_path, deadline)
            archive_path = temporary / "files.tar"
            self._write_file_archive(archive_path, deadline)
            completed_at = datetime.now(timezone.utc).replace(microsecond=0)
            manifest_path = temporary / "manifest.json"
            manifest_path.write_text(
                json.dumps(
                    {
                        "format_version": BACKUP_FORMAT_VERSION,
                        "completed_at": completed_at.isoformat(),
                        "files": [
                            self._manifest_entry(database_path, lambda: self._remaining(deadline)),
                            self._manifest_entry(archive_path, lambda: self._remaining(deadline)),
                        ],
                    },
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                encoding="utf-8",
            )
            _fsync_file(manifest_path)
            manifest_sha256, _ = _sha256_and_size(manifest_path, lambda: self._remaining(deadline))
            final_relative = f"sets/{job_id}-{completed_at.strftime('%Y%m%dT%H%M%SZ')}"
            final_path = _inside(self.root, final_relative)
            final_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            if final_path.exists():
                raise _stable_error("artifact_target_exists", "Backup artifact could not be promoted.")
            validate_backup_set(self.root, temporary.name, ensure_time=lambda: self._remaining(deadline))
            _fsync_directory(temporary)
            os.replace(temporary, final_path)
            _fsync_directory(final_path.parent)
            temporary = None
            promoted = final_path
            manifest = validate_backup_set(
                self.root, final_relative, ensure_time=lambda: self._remaining(deadline)
            )
            result = BackupArtifactResult(
                relative_set_path=final_relative,
                manifest_sha256=manifest_sha256,
                dump_bytes=manifest.files["database.sql"].size,
                archive_bytes=manifest.files["files.tar"].size,
                total_bytes=(
                    manifest.files["database.sql"].size + manifest.files["files.tar"].size
                ),
                completed_at=manifest.completed_at,
            )
            promoted = None
            return result
        except BackupArtifactError:
            raise
        except BackupSetValidationError:
            raise _stable_error("artifact_validation_failed", "Backup artifact validation failed.") from None
        except OSError:
            raise _stable_error("artifact_io_failed", "Backup artifact storage failed.") from None
        finally:
            if temporary is not None:
                self._remove_incomplete_directory(temporary)
            if promoted is not None:
                self._remove_incomplete_directory(promoted)

    @staticmethod
    def _remove_incomplete_directory(directory: Path) -> None:
        try:
            shutil.rmtree(directory)
        except OSError:
            raise _stable_error(
                "artifact_cleanup_failed", "Backup artifact cleanup failed."
            ) from None
        if directory.exists():
            raise _stable_error("artifact_cleanup_failed", "Backup artifact cleanup failed.")

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise _stable_error("backup_attempt_timeout", "Backup attempt timed out.")
        return remaining

    def _write_dump(self, target: Path, deadline: float) -> None:
        if self.dump_runner is not None:
            try:
                self.dump_runner(target)
            except Exception:
                raise _stable_error("dump_failed", "Database export failed.") from None
        else:
            self._run_mysqldump(target, deadline)
        if not target.is_file():
            raise _stable_error("dump_failed", "Database export failed.")
        _fsync_file(target)

    def _run_mysqldump(self, target: Path, deadline: float) -> None:
        if not self.database_url:
            raise _stable_error("dump_configuration_invalid", "Database export configuration is invalid.")
        try:
            url = make_url(self.database_url)
            if not url.drivername.startswith("mysql") or not url.host or not url.database:
                raise ValueError("unsupported database URL")
            command = [
                "mysqldump",
                "--host",
                url.host,
                "--port",
                str(url.port or 3306),
            ]
            if url.username:
                command.extend(["--user", url.username])
            command.extend(["--single-transaction", "--result-file", str(target), url.database])
            environment = dict(os.environ)
            if url.password is not None:
                environment["MYSQL_PWD"] = url.password
            result = self.process_runner(
                command,
                check=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                env=environment,
                timeout=self._remaining(deadline),
            )
            if getattr(result, "returncode", 1) != 0:
                raise RuntimeError("mysqldump failed")
        except BackupArtifactError:
            raise
        except subprocess.TimeoutExpired:
            raise _stable_error("backup_attempt_timeout", "Backup attempt timed out.") from None
        except Exception:
            raise _stable_error("dump_failed", "Database export failed.") from None

    def _write_file_archive(self, target: Path, deadline: float) -> None:
        if self.file_root is None or not self.file_root.is_dir():
            raise _stable_error("file_archive_failed", "File archive creation failed.")
        try:
            root = self.file_root.resolve()
            with tarfile.open(target, mode="w") as archive:
                for source in sorted(root.rglob("*")):
                    self._remaining(deadline)
                    if source.is_symlink():
                        raise ValueError("symlinked storage file")
                    if not source.is_file():
                        continue
                    relative = source.relative_to(root).as_posix()
                    _portable_relative(relative)
                    info = archive.gettarinfo(source, arcname=relative)
                    with source.open("rb", buffering=0) as raw:
                        with _DeadlineReader(
                            cast(io.RawIOBase, raw), lambda: self._remaining(deadline)
                        ) as stream:
                            archive.addfile(info, stream)
            _fsync_file(target)
        except BackupArtifactError:
            raise
        except Exception:
            raise _stable_error("file_archive_failed", "File archive creation failed.") from None

    @staticmethod
    def _manifest_entry(
        path: Path, ensure_time: Callable[[], object] | None = None
    ) -> Mapping[str, object]:
        sha256, size = _sha256_and_size(path, ensure_time)
        return {"path": path.name, "size": size, "sha256": sha256}
