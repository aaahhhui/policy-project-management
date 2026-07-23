from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit


TRACKING_QUERY_PREFIXES = ("utm_",)
TRACKING_QUERY_NAMES = frozenset({"fbclid", "gclid", "mc_cid", "mc_eid"})
_PERCENT_ESCAPE = re.compile(r"%([0-9a-fA-F]{2})")
_UNRESERVED = frozenset("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-._~")


def normalize_text(value: str) -> str:
    return " ".join(value.split())


def normalize_url(url: str) -> str:
    parsed = urlsplit(url.strip())
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        raise ValueError("URL must be an absolute HTTP(S) URL")
    try:
        port = parsed.port
    except ValueError as error:
        raise ValueError("URL contains an invalid port") from error

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.encode("idna").decode("ascii").lower()
    host = f"[{hostname}]" if ":" in hostname else hostname
    if port is not None and port != {"http": 80, "https": 443}[scheme]:
        host = f"{host}:{port}"
    if parsed.username:
        credentials = quote(parsed.username, safe="-._~")
        if parsed.password is not None:
            credentials += f":{quote(parsed.password, safe='-._~')}"
        host = f"{credentials}@{host}"

    path = _canonical_component(parsed.path or "/", safe="/-._~!$&'()*+,;=:@")
    query_pairs = [
        (key, value)
        for key, value in parse_qsl(parsed.query, keep_blank_values=True)
        if not _is_tracking_query(key)
    ]
    query = urlencode(sorted(query_pairs), doseq=True, quote_via=quote, safe="-._~")
    return urlunsplit((scheme, host, path, query, ""))


def content_hash(title: str, body_text: str) -> str:
    content = f"{normalize_text(title)}\n{normalize_text(body_text)}".encode("utf-8")
    return hashlib.sha256(content).hexdigest()


def _is_tracking_query(name: str) -> bool:
    lowered = name.casefold()
    return lowered.startswith(TRACKING_QUERY_PREFIXES) or lowered in TRACKING_QUERY_NAMES


def _canonical_component(value: str, *, safe: str) -> str:
    def replace(match: re.Match[str]) -> str:
        character = chr(int(match.group(1), 16))
        return character if character in _UNRESERVED else match.group(0).upper()

    return quote(_PERCENT_ESCAPE.sub(replace, value), safe=safe + "%")
