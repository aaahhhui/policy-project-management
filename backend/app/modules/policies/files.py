from __future__ import annotations

import os
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePath
from urllib.parse import unquote, urlsplit

import httpx


MAX_ATTACHMENT_BYTES = 30 * 1024 * 1024
ATTACHMENT_TIMEOUT_SECONDS = 20.0
_UNSAFE_FILENAME = re.compile(r"[^\w.() -]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class DownloadedAttachment:
    content: bytes
    content_type: str | None


class HttpAttachmentDownloader:
    def download(self, source_url: str) -> DownloadedAttachment:
        content = bytearray()
        with httpx.stream("GET", source_url, timeout=ATTACHMENT_TIMEOUT_SECONDS, follow_redirects=True) as response:
            response.raise_for_status()
            for chunk in response.iter_bytes():
                content.extend(chunk)
                if len(content) > MAX_ATTACHMENT_BYTES:
                    raise ValueError("attachment exceeds 30 MiB limit")
            return DownloadedAttachment(bytes(content), response.headers.get("content-type"))


class FileStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def save_snapshot(self, policy_id: int, version_number: int, html: str) -> str:
        relative_path = Path("snapshots") / str(policy_id) / str(version_number) / "page.html"
        self._atomic_write(relative_path, html.encode("utf-8"))
        return relative_path.as_posix()

    def save_attachment(
        self, policy_id: int, version_number: int, filename: str, content: bytes
    ) -> str:
        relative_path = Path("attachments") / str(policy_id) / str(version_number) / filename
        self._atomic_write(relative_path, content)
        return relative_path.as_posix()

    def remove_file(self, relative_path: str) -> None:
        target = self._resolve(relative_path)
        try:
            target.unlink()
        except FileNotFoundError:
            return
        parent = target.parent
        while parent != self.root:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent

    def _atomic_write(self, relative_path: Path, content: bytes) -> None:
        target = self._resolve(relative_path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _resolve(self, relative_path: str | Path) -> Path:
        candidate = (self.root / relative_path).resolve()
        root = self.root.resolve()
        if candidate != root and root not in candidate.parents:
            raise ValueError("storage path escapes file root")
        return candidate


def safe_attachment_filename(display_name: str, source_url: str, used_names: Iterable[str]) -> str:
    raw_name = PurePath(display_name.replace("\\", "/")).name.strip()
    if not raw_name or raw_name in {".", ".."}:
        raw_name = PurePath(unquote(urlsplit(source_url).path)).name or "attachment"
    basename = _UNSAFE_FILENAME.sub("_", raw_name).strip(" ._") or "attachment"
    suffix = Path(basename).suffix
    stem = basename[: -len(suffix)] if suffix else basename
    occupied = set(used_names)
    candidate = basename
    sequence = 2
    while candidate.casefold() in {name.casefold() for name in occupied}:
        candidate = f"{stem} ({sequence}){suffix}"
        sequence += 1
    return candidate
