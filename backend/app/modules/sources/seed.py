import sys
from typing import TypedDict

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.modules.auth.models import Role, User
from app.modules.sources.models import PolicySource
from app.modules.sources.schemas import SourceChannelInput, SourceCreate, SourceUpdate
from app.modules.sources.service import SourceService

class _SeedChannel(TypedDict):
    code: str
    name: str
    list_url: str


class _SeedSource(TypedDict):
    name: str
    home_url: str
    adapter_key: str
    channels: list[_SeedChannel]


GDII_SOURCE: _SeedSource = {
    "name": "广东省工业和信息化厅",
    "home_url": "https://gdii.gd.gov.cn/",
    "adapter_key": "gdii",
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


def _payload() -> SourceCreate:
    return SourceCreate(
        name=GDII_SOURCE["name"],
        home_url=GDII_SOURCE["home_url"],
        channels=[SourceChannelInput(**channel) for channel in GDII_SOURCE["channels"]],
    )


def seed_gdii_source(db: Session, actor: User) -> PolicySource:
    service = SourceService(db, actor)
    source = db.scalar(select(PolicySource).where(PolicySource.name == GDII_SOURCE["name"]))
    try:
        if source is None:
            source = service.create(_payload(), adapter_key="gdii")
        else:
            source = service.update(
                source.id,
                SourceUpdate(home_url=GDII_SOURCE["home_url"], channels=_payload().channels, is_enabled=True),
            )
            source.adapter_key = "gdii"
            source.adapter_status = "ready"
            source.updated_by = actor.id
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
