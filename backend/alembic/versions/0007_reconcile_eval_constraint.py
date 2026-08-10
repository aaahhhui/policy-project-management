"""reconcile evaluation constraint and project invariants

Revision ID: 0007_reconcile_eval_constraint
Revises: 0006_stage3_project_ledger
Create Date: 2026-08-10
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import context, op


revision: str = "0007_reconcile_eval_constraint"
down_revision: str | None = "0006_stage3_project_ledger"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

EVALUATION_STATUS_CHECK = (
    "status IN ('pending', 'running', 'succeeded', 'awaiting_confirmation', "
    "'confirmed', 'cancelled', 'failed')"
)

PROJECT_CHECKS = {
    "ck_projects_submission_status_requires_submitted_on": (
        "status NOT IN ('submitted', 'succeeded', 'rejected') OR submitted_on IS NOT NULL"
    ),
    "ck_projects_result_requires_submission_order": (
        "result_on IS NULL OR (submitted_on IS NOT NULL AND result_on >= submitted_on)"
    ),
    "ck_projects_name_nonblank": "length(trim(name)) > 0",
}

LEGACY_PROJECT_DATE_RECONCILIATION = """
UPDATE projects
SET submitted_on = CASE
    WHEN result_on IS NOT NULL THEN COALESCE(
        (
            SELECT history.related_date
            FROM project_status_history AS history
            WHERE history.project_id = projects.id
              AND history.new_status = 'submitted'
              AND history.related_date IS NOT NULL
              AND history.related_date <= projects.result_on
            ORDER BY history.occurred_at DESC, history.id DESC
            LIMIT 1
        ),
        result_on
    )
    ELSE COALESCE(
        (
            SELECT history.related_date
            FROM project_status_history AS history
            WHERE history.project_id = projects.id
              AND history.new_status = 'submitted'
              AND history.related_date IS NOT NULL
            ORDER BY history.occurred_at DESC, history.id DESC
            LIMIT 1
        ),
        DATE(created_at)
    )
END
WHERE (
        status IN ('submitted', 'succeeded', 'rejected')
        AND submitted_on IS NULL
    )
    OR (
        result_on IS NOT NULL
        AND (submitted_on IS NULL OR submitted_on > result_on)
    )
"""


def _check_names(table_name: str) -> set[str]:
    return {
        check["name"]
        for check in sa.inspect(op.get_bind()).get_check_constraints(table_name)
        if check["name"] is not None
    }


def upgrade() -> None:
    # Existing 0006 rows may predate the stricter date invariants. Preserve the
    # workflow status and result date, preferring an exact submitted transition.
    # When no such fact exists, the result date (or, last, creation date) is a
    # deliberate lossy fallback that produces the earliest defensible ordering.
    op.execute(sa.text(LEGACY_PROJECT_DATE_RECONCILIATION))

    if context.is_offline_mode():
        with op.batch_alter_table("evaluation_batches") as batch_op:
            batch_op.drop_constraint("evaluation_status_v2_code", type_="check")
            batch_op.create_check_constraint(
                "evaluation_status_v3_code", EVALUATION_STATUS_CHECK
            )
        with op.batch_alter_table("projects") as batch_op:
            for name, condition in PROJECT_CHECKS.items():
                batch_op.create_check_constraint(name, condition)
        return

    evaluation_checks = _check_names("evaluation_batches")
    if "evaluation_status_v2_code" in evaluation_checks:
        with op.batch_alter_table("evaluation_batches") as batch_op:
            batch_op.drop_constraint("evaluation_status_v2_code", type_="check")
            batch_op.create_check_constraint(
                "evaluation_status_v3_code", EVALUATION_STATUS_CHECK
            )

    project_checks = _check_names("projects")
    missing_checks = PROJECT_CHECKS.keys() - project_checks
    if missing_checks:
        with op.batch_alter_table("projects") as batch_op:
            for name in missing_checks:
                batch_op.create_check_constraint(name, PROJECT_CHECKS[name])


def downgrade() -> None:
    if context.is_offline_mode():
        with op.batch_alter_table("projects") as batch_op:
            for name in PROJECT_CHECKS:
                batch_op.drop_constraint(name, type_="check")
        with op.batch_alter_table("evaluation_batches") as batch_op:
            batch_op.drop_constraint("evaluation_status_v3_code", type_="check")
            batch_op.create_check_constraint(
                "evaluation_status_v2_code", EVALUATION_STATUS_CHECK
            )
        return

    project_checks = _check_names("projects")
    existing_checks = PROJECT_CHECKS.keys() & project_checks
    if existing_checks:
        with op.batch_alter_table("projects") as batch_op:
            for name in existing_checks:
                batch_op.drop_constraint(name, type_="check")

    evaluation_checks = _check_names("evaluation_batches")
    if "evaluation_status_v3_code" in evaluation_checks:
        with op.batch_alter_table("evaluation_batches") as batch_op:
            batch_op.drop_constraint("evaluation_status_v3_code", type_="check")
            batch_op.create_check_constraint(
                "evaluation_status_v2_code", EVALUATION_STATUS_CHECK
            )
