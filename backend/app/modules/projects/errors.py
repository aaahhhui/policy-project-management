from __future__ import annotations

from typing import ClassVar


class ProjectError(Exception):
    code: ClassVar[str] = "project_error"

    def __init__(self, **public_context: object) -> None:
        self.public_context = public_context
        super().__init__(self.code)


class PolicyNotConvertible(ProjectError):
    code = "policy_not_convertible"


class PolicyAlreadyConverted(ProjectError):
    code = "policy_already_converted"


class PrimaryEntityMissing(ProjectError):
    code = "primary_entity_missing"


class ProjectLiaisonRequired(ProjectError):
    code = "project_liaison_required"


class ProjectUserInactive(ProjectError):
    code = "project_user_inactive"


class ProjectWriteForbidden(ProjectError):
    code = "project_write_forbidden"


class ProjectTransitionInvalid(ProjectError):
    code = "project_transition_invalid"


class ProjectCorrectionInvalid(ProjectError):
    code = "project_correction_invalid"


class ProjectFieldValidationFailed(ProjectError):
    code = "project_field_validation_failed"


class ProjectVersionConflict(ProjectError):
    code = "project_version_conflict"


class IdempotencyKeyReused(ProjectError):
    code = "idempotency_key_reused"
