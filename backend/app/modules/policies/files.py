from __future__ import annotations

import ipaddress
import errno
import os
import re
import socket
import time
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path, PurePath
from typing import Any, Callable
from urllib.parse import unquote, urljoin, urlsplit

import httpx


MAX_ATTACHMENT_BYTES = 30 * 1024 * 1024
ATTACHMENT_TIMEOUT_SECONDS = 20.0
_UNSAFE_FILENAME = re.compile(r"[^\w.() -]+", re.UNICODE)


@dataclass(frozen=True, slots=True)
class DownloadedAttachment:
    content: bytes
    content_type: str | None


class HttpAttachmentDownloader:
    def __init__(
        self,
        *,
        client_factory: Callable[[], Any] = httpx.Client,
        resolver: Callable[[str], list[str]] | None = None,
        clock: Callable[[], float] = time.monotonic,
        max_redirects: int = 5,
    ) -> None:
        self.client_factory = client_factory
        self.resolver = resolver or _resolve_host
        self.clock = clock
        self.max_redirects = max_redirects

    def download(self, source_url: str) -> DownloadedAttachment:
        deadline = self.clock() + ATTACHMENT_TIMEOUT_SECONDS
        url = source_url
        client = self.client_factory()
        try:
            for _ in range(self.max_redirects + 1):
                self._validate_url(url)
                response_context = client.stream(
                    "GET", url, timeout=self._remaining(deadline), follow_redirects=False
                )
                with response_context as response:
                    if 300 <= response.status_code < 400:
                        location = response.headers.get("location")
                        if not location:
                            raise ValueError("attachment redirect has no location")
                        url = urljoin(url, location)
                        continue
                    response.raise_for_status()
                    content_length = response.headers.get("content-length")
                    if content_length is not None and int(content_length) > MAX_ATTACHMENT_BYTES:
                        raise ValueError("attachment exceeds 30 MiB limit")
                    content = bytearray()
                    for chunk in response.iter_bytes():
                        if self.clock() > deadline:
                            raise TimeoutError("attachment download exceeded 20 second deadline")
                        content.extend(chunk)
                        if len(content) > MAX_ATTACHMENT_BYTES:
                            raise ValueError("attachment exceeds 30 MiB limit")
                    return DownloadedAttachment(bytes(content), response.headers.get("content-type"))
            raise ValueError("attachment exceeded redirect limit")
        finally:
            client.close()

    def _remaining(self, deadline: float) -> float:
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise TimeoutError("attachment download exceeded 20 second deadline")
        return remaining

    def _validate_url(self, url: str) -> None:
        parsed = urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("attachment URL must use HTTP(S) with a host")
        if parsed.username is not None or parsed.password is not None:
            raise ValueError("attachment URL credentials are not allowed")
        addresses = self.resolver(parsed.hostname)
        if not addresses or any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise ValueError("attachment URL host is not publicly routable")


def _resolve_host(hostname: str) -> list[str]:
    return list(
        {str(entry[4][0]) for entry in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)}
    )


class FileStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()

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
        if target.exists():
            raise FileExistsError(f"refusing to overwrite existing storage path: {relative_path}")
        temporary = target.with_name(f".{target.name}.{uuid.uuid4().hex}.tmp")
        try:
            with temporary.open("xb") as output:
                output.write(content)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, target)
            self._fsync_directory(target.parent)
        except Exception:
            temporary.unlink(missing_ok=True)
            raise

    def _resolve(self, relative_path: str | Path) -> Path:
        candidate = (self.root / relative_path).resolve()
        if candidate != self.root and self.root not in candidate.parents:
            raise ValueError("storage path escapes file root")
        return candidate

    @staticmethod
    def _fsync_directory(directory: Path) -> None:
        try:
            descriptor = os.open(directory, os.O_RDONLY)
            try:
                os.fsync(descriptor)
            finally:
                os.close(descriptor)
        except OSError as error:
            unsupported = {errno.EINVAL, errno.ENOTSUP, getattr(errno, "EOPNOTSUPP", errno.ENOTSUP)}
            if os.name == "nt":
                unsupported.add(errno.EACCES)
            if error.errno not in unsupported:
                raise


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
