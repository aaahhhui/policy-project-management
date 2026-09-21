import hashlib
import json
from datetime import timezone
from pathlib import Path
import subprocess

import pytest

from app.modules.backups.artifacts import (
    BackupArtifactError,
    BackupArtifactWriter,
    BackupSetValidationError,
    validate_backup_set,
)


def _write_manifest(
    root: Path, files: list[dict[str, object]], version: int = 1, set_name: str = "set-17"
) -> None:
    backup_set = root / set_name
    backup_set.mkdir(parents=True, exist_ok=True)
    (backup_set / "manifest.json").write_text(
        json.dumps(
            {
                "format_version": version,
                "completed_at": "2026-08-20T03:30:00+00:00",
                "files": files,
            }
        ),
        encoding="utf-8",
    )


def _file_entry(name: str, content: bytes) -> dict[str, object]:
    return {
        "path": name,
        "size": len(content),
        "sha256": hashlib.sha256(content).hexdigest(),
    }


def _write_complete_set(root: Path, set_name: str = "set-17") -> Path:
    backup_set = root / set_name
    backup_set.mkdir(parents=True, exist_ok=True)
    database_content = b"sql"
    archive_content = b"tar"
    (backup_set / "database.sql").write_bytes(database_content)
    (backup_set / "files.tar").write_bytes(archive_content)
    _write_manifest(
        root,
        [
            _file_entry("database.sql", database_content),
            _file_entry("files.tar", archive_content),
        ],
        set_name=set_name,
    )
    return backup_set


def test_writer_promotes_only_verified_complete_set(tmp_path: Path) -> None:
    file_root = tmp_path / "files"
    file_root.mkdir()
    (file_root / "page.html").write_text("captured page", encoding="utf-8")

    result = BackupArtifactWriter(
        tmp_path,
        dump_runner=lambda target: target.write_bytes(b"sql"),
        file_root=file_root,
    ).create(17)

    final = tmp_path / result.relative_set_path
    assert final.joinpath("manifest.json").is_file()
    assert not list(tmp_path.glob(".tmp-*"))
    assert validate_backup_set(tmp_path, result.relative_set_path).files["database.sql"].sha256
    assert result.completed_at.tzinfo is timezone.utc
    assert result.dump_bytes == 3
    assert result.total_bytes == result.dump_bytes + result.archive_bytes


def test_writer_removes_temporary_output_and_exposes_stable_dump_failure(tmp_path: Path) -> None:
    def failing_dump(_: Path) -> None:
        raise RuntimeError("database password must never escape")

    with pytest.raises(BackupArtifactError, match="dump_failed") as error:
        BackupArtifactWriter(tmp_path, dump_runner=failing_dump, file_root=tmp_path / "files").create(17)

    assert error.value.summary == "Database export failed."
    assert error.value.__cause__ is None
    assert not list(tmp_path.glob(".tmp-*"))


@pytest.mark.parametrize(
    ("entry", "code"),
    [
        (_file_entry("/absolute", b"x"), "manifest_path_invalid"),
        (_file_entry("../outside", b"x"), "manifest_path_invalid"),
        (_file_entry(r"C:\\outside", b"x"), "manifest_path_invalid"),
    ],
)
def test_validation_rejects_nonportable_manifest_paths(
    tmp_path: Path, entry: dict[str, object], code: str
) -> None:
    _write_manifest(tmp_path, [entry])

    with pytest.raises(BackupSetValidationError, match=code):
        validate_backup_set(tmp_path, "set-17")


def test_validation_rejects_duplicate_manifest_paths(tmp_path: Path) -> None:
    (tmp_path / "set-17").mkdir()
    content = b"sql"
    (tmp_path / "set-17" / "database.sql").write_bytes(content)
    entry = _file_entry("database.sql", content)
    _write_manifest(tmp_path, [entry, entry])

    with pytest.raises(BackupSetValidationError, match="manifest_duplicate_path"):
        validate_backup_set(tmp_path, "set-17")


def test_validation_rejects_missing_manifest_file(tmp_path: Path) -> None:
    _write_manifest(
        tmp_path,
        [_file_entry("database.sql", b"sql"), _file_entry("files.tar", b"tar")],
    )

    with pytest.raises(BackupSetValidationError, match="manifest_file_missing"):
        validate_backup_set(tmp_path, "set-17")


def test_validation_rejects_unsupported_format_version(tmp_path: Path) -> None:
    _write_manifest(tmp_path, [], version=2)

    with pytest.raises(BackupSetValidationError, match="manifest_version_unsupported"):
        validate_backup_set(tmp_path, "set-17")


def test_validation_rejects_a_symlinked_set_even_when_target_is_inside_root(tmp_path: Path) -> None:
    _write_complete_set(tmp_path, "target-set")
    try:
        (tmp_path / "set-17").symlink_to("target-set", target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error.winerror or error.errno}")

    with pytest.raises(BackupSetValidationError, match="manifest_path_invalid"):
        validate_backup_set(tmp_path, "set-17")


def test_validation_rejects_an_intermediate_symlink_even_when_target_is_inside_root(
    tmp_path: Path,
) -> None:
    _write_complete_set(tmp_path / "target-sets")
    try:
        (tmp_path / "sets").symlink_to("target-sets", target_is_directory=True)
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error.winerror or error.errno}")

    with pytest.raises(BackupSetValidationError, match="manifest_path_invalid"):
        validate_backup_set(tmp_path, "sets/set-17")


def test_validation_rejects_a_symlinked_artifact_even_when_target_is_inside_set(
    tmp_path: Path,
) -> None:
    backup_set = _write_complete_set(tmp_path)
    (backup_set / "database-copy.sql").write_bytes(b"sql")
    (backup_set / "database.sql").unlink()
    try:
        (backup_set / "database.sql").symlink_to("database-copy.sql")
    except OSError as error:
        pytest.skip(f"symlink creation unavailable: {error.winerror or error.errno}")

    with pytest.raises(BackupSetValidationError, match="manifest_path_invalid"):
        validate_backup_set(tmp_path, "set-17")


def test_validation_rejects_unexpected_set_entry(tmp_path: Path) -> None:
    backup_set = _write_complete_set(tmp_path)
    (backup_set / "unexpected.txt").write_text("unexpected", encoding="utf-8")

    with pytest.raises(BackupSetValidationError, match="manifest_unexpected_entry"):
        validate_backup_set(tmp_path, "set-17")


@pytest.mark.parametrize(
    ("stored_size", "stored_digest", "code"),
    [
        (4, hashlib.sha256(b"sql").hexdigest(), "manifest_size_invalid"),
        (3, "0" * 64, "manifest_checksum_invalid"),
    ],
)
def test_validation_rejects_tampered_file_metadata(
    tmp_path: Path, stored_size: int, stored_digest: str, code: str
) -> None:
    backup_set = tmp_path / "set-17"
    backup_set.mkdir()
    (backup_set / "database.sql").write_bytes(b"sql")
    (backup_set / "files.tar").write_bytes(b"tar")
    _write_manifest(
        tmp_path,
        [
            {"path": "database.sql", "size": stored_size, "sha256": stored_digest},
            _file_entry("files.tar", b"tar"),
        ],
    )

    with pytest.raises(BackupSetValidationError, match=code):
        validate_backup_set(tmp_path, "set-17")


def test_writer_uses_environment_for_database_password_not_command_arguments(tmp_path: Path) -> None:
    commands: list[list[str]] = []
    environments: list[dict[str, str]] = []

    def process_runner(command: list[str], *, env: dict[str, str], **_: object) -> object:
        commands.append(command)
        environments.append(env)
        Path(command[command.index("--result-file") + 1]).write_bytes(b"sql")

        class Result:
            returncode = 0

        return Result()

    file_root = tmp_path / "files"
    file_root.mkdir()
    result = BackupArtifactWriter(
        tmp_path,
        database_url="mysql+pymysql://backup_user:password@db:3307/policy",
        file_root=file_root,
        process_runner=process_runner,
    ).create(17)

    assert (tmp_path / result.relative_set_path / "database.sql").is_file()
    assert commands[0][:8] == [
        "mysqldump",
        "--host",
        "db",
        "--port",
        "3307",
        "--user",
        "backup_user",
        "--single-transaction",
    ]
    assert Path(commands[0][commands[0].index("--result-file") + 1]).name == "database.sql"
    assert commands[0][-1] == "policy"
    assert environments[0]["MYSQL_PWD"] == "password"
    assert "password" not in " ".join(commands[0])


def test_dump_timeout_stops_attempt_and_removes_partial_set(tmp_path: Path) -> None:
    file_root = tmp_path / "files"
    file_root.mkdir()

    def timed_out_runner(command: list[str], *, timeout: float, **_: object) -> object:
        assert 0 < timeout <= 25
        raise subprocess.TimeoutExpired(command, timeout)

    with pytest.raises(BackupArtifactError) as error:
        BackupArtifactWriter(
            tmp_path,
            database_url="mysql+pymysql://backup_user:password@db:3307/policy",
            file_root=file_root,
            timeout_seconds=25,
            process_runner=timed_out_runner,
        ).create(17)

    assert error.value.code == "backup_attempt_timeout"
    assert not list(tmp_path.glob(".tmp-*"))


def test_archive_respects_remaining_attempt_deadline(tmp_path: Path) -> None:
    file_root = tmp_path / "files"
    file_root.mkdir()
    (file_root / "policy.html").write_text("test", encoding="utf-8")
    clock_state = {"now": 0.0}

    def dump_runner(target: Path) -> None:
        target.write_bytes(b"sql")
        clock_state["now"] = 30.0

    with pytest.raises(BackupArtifactError) as error:
        BackupArtifactWriter(
            tmp_path,
            dump_runner=dump_runner,
            file_root=file_root,
            timeout_seconds=25,
            clock=lambda: clock_state["now"],
        ).create(17)

    assert error.value.code == "backup_attempt_timeout"
    assert not list(tmp_path.glob(".tmp-*"))


def test_writer_surfaces_stable_cleanup_failure_without_leaving_cleanup_best_effort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.backups import artifacts

    def failing_cleanup(_: Path, **__: object) -> None:
        raise OSError("cannot remove sensitive temporary export")

    monkeypatch.setattr(artifacts.shutil, "rmtree", failing_cleanup)

    with pytest.raises(BackupArtifactError, match="artifact_cleanup_failed") as error:
        BackupArtifactWriter(
            tmp_path,
            dump_runner=lambda _: (_ for _ in ()).throw(RuntimeError("dump failed")),
            file_root=tmp_path / "files",
        ).create(17)

    assert error.value.summary == "Backup artifact cleanup failed."
    assert error.value.__cause__ is None
    assert "sensitive temporary export" not in str(error.value)


def test_writer_checks_that_cleanup_removed_the_temporary_directory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.backups import artifacts

    monkeypatch.setattr(artifacts.shutil, "rmtree", lambda *_: None)

    with pytest.raises(BackupArtifactError, match="artifact_cleanup_failed"):
        BackupArtifactWriter(
            tmp_path,
            dump_runner=lambda _: (_ for _ in ()).throw(RuntimeError("dump failed")),
            file_root=tmp_path / "files",
        ).create(17)

    assert list(tmp_path.glob(".tmp-*"))


def test_writer_removes_promoted_set_when_post_promotion_validation_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.modules.backups import artifacts

    real_validator = artifacts.validate_backup_set
    calls = 0

    def fail_only_after_promotion(root: Path, relative_set_path: str, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise BackupSetValidationError("manifest_checksum_invalid")
        return real_validator(root, relative_set_path, **kwargs)

    monkeypatch.setattr(artifacts, "validate_backup_set", fail_only_after_promotion)
    file_root = tmp_path / "files"
    file_root.mkdir()

    with pytest.raises(BackupArtifactError, match="artifact_validation_failed"):
        BackupArtifactWriter(
            tmp_path,
            dump_runner=lambda target: target.write_bytes(b"sql"),
            file_root=file_root,
        ).create(17)

    sets_root = tmp_path / "sets"
    assert not sets_root.exists() or not list(sets_root.iterdir())
