import re
import unicodedata

LOGIN_NAME_MAX_LENGTH = 255
_CANONICAL_LOGIN_PATTERN = re.compile(r"[a-z0-9._-]{1,255}\Z")


def normalize_login_for_auth(login_name: str) -> str | None:
    normalized = unicodedata.normalize("NFKC", login_name).strip().casefold()
    return normalized if _CANONICAL_LOGIN_PATTERN.fullmatch(normalized) else None


def validate_canonical_seed_login(login_name: str) -> str:
    normalized = normalize_login_for_auth(login_name)
    if normalized is None or login_name != normalized:
        raise ValueError("Seed login names must be lowercase ASCII identifiers.")
    return login_name
