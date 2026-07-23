from app.modules.policies.normalize import content_hash, normalize_url


def test_normalize_url_canonicalizes_scheme_host_default_port_tracking_fragment_and_encoding() -> None:
    assert normalize_url(
        " HTTPS://ExAmPlE.Test:443/a%7Eb?b=2&utm_source=news&a=%E4%B8%AD#section "
    ) == "https://example.test/a~b?a=%E4%B8%AD&b=2"


def test_normalize_url_preserves_non_tracking_query_values() -> None:
    assert normalize_url("http://example.test:80/path?topic=grants&gclid=ignored") == (
        "http://example.test/path?topic=grants"
    )


def test_content_hash_ignores_insignificant_whitespace() -> None:
    assert content_hash("  Policy\tTitle ", "first\n\n  second") == content_hash(
        "Policy Title", "first second"
    )
