import pytest

from app.modules.sources import schemas
from app.modules.sources.models import PolicySource
from app.modules.sources.schemas import SourceCreate
from app.modules.sources.service import SourceService


def test_source_labels_trim_stably_dedupe_and_enforce_item_length() -> None:
    payload = SourceCreate(
        name="Public feed",
        entry_url="https://public.example/feed.xml",
        region_labels=["  Guangdong  ", "Guangdong", "广东", " 广东 "],
        topic_labels=["Funding", " Funding ", "Manufacturing"],
    )

    assert payload.region_labels == ["Guangdong", "广东"]
    assert payload.topic_labels == ["Funding", "Manufacturing"]
    with pytest.raises(ValueError, match="at most 64 characters"):
        SourceCreate(
            name="Public feed",
            entry_url="https://public.example/feed.xml",
            region_labels=["x" * 65],
        )


def test_legacy_owner_mutation_footguns_are_absent() -> None:
    assert "home_url" not in PolicySource.__dict__
    assert not hasattr(schemas, "SourceUpdate")
    assert not hasattr(schemas, "SourceChannelInput")
    assert not hasattr(schemas, "SourceChannelResponse")
    assert not hasattr(SourceService, "_channel")
    assert not hasattr(SourceService, "_reconcile_channels")
