from sqlalchemy import select
import pytest

from app.modules.collection.models import CollectionTask
from app.modules.sources.models import PolicySource, SourceChannel
from app.modules.sources.schemas import SourceChannelInput, SourceCreate, SourceUpdate
from app.modules.sources.seed import GDII_SOURCE, seed_gdii_source
from app.modules.sources.service import SourceConflict, SourceNotCollectable, SourceService


def test_new_unrecognized_source_is_pending_and_records_scalar_audit_ids(db, seeded_owner):
    source = SourceService(db, seeded_owner).create(
        SourceCreate(name="  Example source  ", home_url="https://example.com", channels=[])
    )

    assert source.name == "Example source"
    assert source.adapter_status == "pending"
    assert source.adapter_key is None
    assert source.created_by == seeded_owner.id
    assert source.updated_by == seeded_owner.id


def test_pending_and_disabled_sources_cannot_collect(db, seeded_owner):
    service = SourceService(db, seeded_owner)
    pending = service.create(SourceCreate(name="Pending", home_url="https://pending.example", channels=[]))
    ready = service.create(
        SourceCreate(name="Ready", home_url="https://ready.example", channels=[]), adapter_key="gdii"
    )
    service.toggle(ready.id)

    with pytest.raises(SourceNotCollectable, match="adapter"):
        SourceService(db, None).assert_collectable(pending.id)
    with pytest.raises(SourceNotCollectable, match="disabled"):
        SourceService(db, None).assert_collectable(ready.id)


def test_create_rejects_duplicate_names_and_duplicate_channel_codes(db, seeded_owner):
    service = SourceService(db, seeded_owner)
    service.create(SourceCreate(name="Unique", home_url="https://first.example", channels=[]))

    with pytest.raises(SourceConflict, match="name"):
        service.create(SourceCreate(name=" Unique ", home_url="https://second.example", channels=[]))
    with pytest.raises(ValueError, match="channel code"):
        SourceCreate(
            name="Channels",
            home_url="https://channels.example",
            channels=[
                SourceChannelInput(code="notices", name="Notices", list_url="https://a.example"),
                SourceChannelInput(code=" notices ", name="Duplicate", list_url="https://b.example"),
            ],
        )


@pytest.mark.parametrize(
    "url",
    [
        "example.com",
        "ftp://example.com",
        "/relative",
        "https://exa mple.com",
        "https://user:password@example.com",
        "https://",
    ],
)
def test_create_rejects_non_absolute_http_urls(url):
    with pytest.raises(ValueError):
        SourceCreate(name="Invalid URL", home_url=url, channels=[])


def test_source_urls_trim_and_normalize_http_urls_with_localhost_and_ip_support():
    source = SourceCreate(
        name="Normalized",
        home_url="  https://Example.COM/source  ",
        channels=[
            SourceChannelInput(
                code="local",
                name="Local",
                list_url=" http://localhost:8080/policies ",
            ),
            SourceChannelInput(
                code="ip",
                name="IP",
                list_url="https://127.0.0.1:8443/notices",
            ),
        ],
    )

    assert source.home_url == "https://example.com/source"
    assert source.channels[0].list_url == "http://localhost:8080/policies"
    assert source.channels[1].list_url == "https://127.0.0.1:8443/notices"


def test_channel_reconciliation_is_atomic_and_preserves_removed_channel_history(db, seeded_owner):
    service = SourceService(db, seeded_owner)
    source = service.create(
        SourceCreate(
            name="Atomic",
            home_url="https://atomic.example",
            channels=[
                SourceChannelInput(code="notices", name="Notices", list_url="https://atomic.example/notices"),
                SourceChannelInput(code="funds", name="Funds", list_url="https://atomic.example/funds"),
            ],
        )
    )
    notices = next(channel for channel in source.channels if channel.code == "notices")
    db.add(CollectionTask(source_id=source.id, trigger_type="manual", status="succeeded"))
    db.commit()

    updated = service.update(
        source.id,
        SourceUpdate(
            channels=[
                SourceChannelInput(
                    code="notices", name="New notices", list_url="https://atomic.example/new-notices"
                )
            ]
        ),
    )

    channel_by_code = {channel.code: channel for channel in updated.channels}
    assert channel_by_code["notices"].id == notices.id
    assert channel_by_code["notices"].name == "New notices"
    assert channel_by_code["funds"].is_enabled is False
    assert db.scalar(select(CollectionTask).where(CollectionTask.source_id == source.id)) is not None

    with pytest.raises(ValueError, match="channel code"):
        service.update(
            source.id,
            SourceUpdate(
                channels=[
                    SourceChannelInput(code="notices", name="One", list_url="https://atomic.example/one"),
                    SourceChannelInput(code="notices", name="Two", list_url="https://atomic.example/two"),
                ]
            ),
        )
    assert {channel.code: channel.name for channel in db.scalars(select(SourceChannel))} == {
        "notices": "New notices",
        "funds": "Funds",
    }


def test_gdii_seed_is_idempotent_and_ready_with_exact_channels(db, seeded_owner):
    seed_gdii_source(db, seeded_owner)
    seed_gdii_source(db, seeded_owner)

    source = db.scalar(select(PolicySource).where(PolicySource.name == GDII_SOURCE["name"]))
    assert source is not None
    assert source.adapter_key == "gdii"
    assert source.adapter_status == "ready"
    assert source.home_url == GDII_SOURCE["home_url"]
    assert [(channel.code, channel.list_url) for channel in source.channels] == [
        ("notices", "https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html"),
        ("funds", "https://gdii.gd.gov.cn/xmzj1033/index.html"),
    ]
    assert len(list(db.scalars(select(PolicySource)))) == 1
