from sqlalchemy import case, select
from sqlalchemy.orm import Session

from app.modules.profiles.models import BusinessEntity, EnterpriseProfile

ENTITY_ORDER = ("ENTITY-BEIJING", "ENTITY-SUZHOU", "ENTITY-SHENZHEN")


class ProfileService:
    def __init__(self, db: Session) -> None:
        self.db = db

    def get_shared_profile(self) -> EnterpriseProfile | None:
        return self.db.scalar(
            select(EnterpriseProfile).where(EnterpriseProfile.code == "COMPANY-SHARED")
        )

    def list_business_entities(self) -> list[BusinessEntity]:
        return list(
            self.db.scalars(
                select(BusinessEntity)
                .where(BusinessEntity.seed_code.in_(ENTITY_ORDER))
                .order_by(
                    case(
                        {seed_code: position for position, seed_code in enumerate(ENTITY_ORDER)},
                        value=BusinessEntity.seed_code,
                    )
                )
            )
        )
