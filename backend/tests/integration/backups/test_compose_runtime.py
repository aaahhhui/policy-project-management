"""Exercise the resolved Compose contract for the backup worker."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class BackupComposeRuntimeTest(unittest.TestCase):
    def test_backup_worker_uses_the_mounted_container_root(self) -> None:
        if shutil.which("docker") is None:
            self.skipTest("Docker Compose is unavailable")
        compose_version = subprocess.run(
            ["docker", "compose", "version"],
            check=False,
            capture_output=True,
            timeout=10,
        )
        if compose_version.returncode != 0:
            self.skipTest("Docker Compose is unavailable")

        repository = Path(__file__).resolve().parents[4]
        with tempfile.TemporaryDirectory(prefix="stage5-compose-contract-") as temporary:
            root = Path(temporary)
            shutil.copyfile(repository / "compose.yaml", root / "compose.yaml")
            host_backup_root = root / "external-backups"
            (root / ".env").write_text(
                "\n".join(
                    (
                        "MYSQL_DATABASE=policy",
                        "MYSQL_USER=policy",
                        "MYSQL_PASSWORD=test-password",
                        "MYSQL_ROOT_PASSWORD=test-root-password",
                        f"BACKUP_ROOT={host_backup_root.as_posix()}",
                    )
                ),
                encoding="utf-8",
            )
            environment = os.environ.copy()
            for name in (
                "MYSQL_DATABASE",
                "MYSQL_USER",
                "MYSQL_PASSWORD",
                "MYSQL_ROOT_PASSWORD",
                "BACKUP_ROOT",
            ):
                environment.pop(name, None)
            result = subprocess.run(
                [
                    "docker", "compose", "-p", "stage5-backup-contract",
                    "--env-file", str(root / ".env"), "-f", str(root / "compose.yaml"),
                    "config", "--format", "json",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
                env=environment,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            config = json.loads(result.stdout)
            self.assertEqual(
                config["services"]["backup"]["environment"]["BACKUP_ROOT"],
                "/runtime/backups",
            )
            backup_mounts = [
                volume
                for volume in config["services"]["backup"]["volumes"]
                if volume["target"] == "/runtime/backups"
            ]
            self.assertEqual(len(backup_mounts), 1)
            self.assertEqual(backup_mounts[0]["type"], "bind")
            self.assertEqual(
                Path(backup_mounts[0]["source"]).resolve(), host_backup_root.resolve()
            )


if __name__ == "__main__":
    unittest.main()
