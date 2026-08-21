import sys
from datetime import UTC, datetime
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.auth.models import Role, User
from app.modules.sources.models import PolicySource, SourceChannel

class _SeedChannel(TypedDict):
    code: str
    name: str
    list_url: str


class _SeedSource(TypedDict):
    name: str
    entry_url: str
    channels: list[_SeedChannel]


GDII_SOURCE: _SeedSource = {
    "name": "广东省工业和信息化厅",
    "entry_url": "https://gdii.gd.gov.cn/",
    "channels": [
        {
            "code": "notices",
            "name": "通知公告",
            "list_url": "https://gdii.gd.gov.cn/zwgk/tzgg1011/index.html",
        },
        {
            "code": "funds",
            "name": "项目资金",
            "list_url": "https://gdii.gd.gov.cn/xmzj1033/index.html",
        },
    ],
}


def _server_channel(channel: _SeedChannel) -> SourceChannel:
    return SourceChannel(**channel, is_enabled=True)


def _sync_server_channels(source: PolicySource) -> None:
    existing = {channel.code: channel for channel in source.channels}
    for channel in GDII_SOURCE["channels"]:
        current = existing.get(channel["code"])
        if current is None:
            source.channels.append(_server_channel(channel))
            continue
        current.name = channel["name"]
        current.list_url = channel["list_url"]
        current.is_enabled = True


def _new_seed_source(actor: User) -> PolicySource:
    source = PolicySource(
        name=GDII_SOURCE["name"],
        entry_url=GDII_SOURCE["entry_url"],
        adapter_key="gdii",
        adapter_status="ready",
        recognition_status="ready_to_enable",
        recognition_kind="supported_government_site",
        recognition_summary="广东省工业和信息化厅 · 公开政策列表",
        previewed_at=datetime.now(UTC),
        is_enabled=False,
        created_by=actor.id,
        updated_by=actor.id,
    )
    source.channels = [_server_channel(channel) for channel in GDII_SOURCE["channels"]]
    return source


def seed_gdii_source(db: Session, actor: User) -> PolicySource:
    source = db.scalar(select(PolicySource).where(PolicySource.name == GDII_SOURCE["name"]))
    try:
        if source is None:
            source = _new_seed_source(actor)
            db.add(source)
        else:
            source.entry_url = GDII_SOURCE["entry_url"]
            source.adapter_key = "gdii"
            source.adapter_status = "ready"
            source.updated_by = actor.id
            _sync_server_channels(source)
            if source.recognition_status not in {"enabled", "disabled"}:
                source.recognition_status = "ready_to_enable"
                source.recognition_kind = "supported_government_site"
                source.recognition_summary = "广东省工业和信息化厅 · 公开政策列表"
                source.previewed_at = datetime.now(UTC)
                source.is_enabled = False
                source.owner_confirmed_at = None
                source.enabled_at = None
                source.disabled_at = None
        db.commit()
    except Exception:
        db.rollback()
        raise
    return source


def main() -> None:
    with SessionLocal() as db:
        actor = db.scalar(
            select(User).join(User.roles).where(Role.code == "applicant_owner").order_by(User.id)
        )
        if actor is None:
            raise SystemExit("An applicant_owner user is required before seeding sources.")
        seed_gdii_source(db, actor)


if __name__ == "__main__":
    if len(sys.argv) != 1:
        raise SystemExit("Usage: python -m app.modules.sources.seed")
    main()
