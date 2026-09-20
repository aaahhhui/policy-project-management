from pathlib import Path


def test_stage5_uat_guide_covers_manual_backup_isolated_recovery_and_secret_safety() -> None:
    """A missing critical operator step would make the acceptance guide unsafe to use."""
    guide = (
        Path(__file__).resolve().parents[4] / "docs" / "stage5-backup-recovery-uat.md"
    ).read_text(encoding="utf-8")

    assert "POST /api/backups" in guide
    assert "stage5-recovery-uat" in guide
    assert "WECOM_WEBHOOK_URL" not in guide
    assert "https://qyapi.weixin.qq.com/" not in guide
    assert "DATABASE_URL=invalid" not in guide
    assert "FILE_STORAGE_ROOT=/nonexistent" in guide
    assert "Set-Location .." in guide
    acceptance_project = "stage5-backup-uat"
    acceptance_commands = [
        line.strip()
        for line in guide.splitlines()
        if line.strip().startswith("docker compose") and "stage5-recovery" not in line
    ]
    assert acceptance_commands
    assert all(f"-p {acceptance_project}" in command for command in acceptance_commands)
    assert "Record the test job ID before any one-iteration worker command." in guide
    assert "Before **every** one-iteration worker command" in guide
    assert "GET /api/backups?status=pending" in guide
    assert "GET /api/backups?status=retry_wait" in guide
