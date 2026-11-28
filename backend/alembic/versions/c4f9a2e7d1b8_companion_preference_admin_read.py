"""Let root read companion preferences under the companion admin scope.

Revision ID: c4f9a2e7d1b8
Revises: b3e8f5a1d6c7
Create Date: 2026-11-28

The admin companion view shows which companion an account picked and whether it
is turned on. ``companion_preference`` stays owner-writable only; this adds a
SELECT-only ``companion_preference_companion_admin_read`` policy that applies
when the transaction carries ``app.user_role = 'root'`` and
``app.admin_scope = 'companion'``.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "c4f9a2e7d1b8"
down_revision: str | None = "b3e8f5a1d6c7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

APP_ROLE = "apsor_app"
ADMIN_CHECK = (
    "current_setting('app.user_role', true) = 'root' "
    "AND current_setting('app.admin_scope', true) = 'companion'"
)


def upgrade() -> None:
    op.execute(
        "CREATE POLICY companion_preference_companion_admin_read ON companion_preference "
        f"FOR SELECT TO {APP_ROLE} USING ({ADMIN_CHECK})"
    )


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS companion_preference_companion_admin_read ON companion_preference"
    )
