"""pstn_inn_cache_operators + pstn_inn_ranges_cache + sync_schedule setting

Revision ID: 0011_pstn_inn_cache
Revises: 0010_sync_runs
Create Date: 2026-08-03
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0011_pstn_inn_cache"
down_revision: Union[str, None] = "0010_sync_runs"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

REQUIRED_OPERATORS = [
    ("ООО «СИПАУТНЭТ»", "5920032027"),
    ("ООО «ИНТЕРНОД»", "7733808377"),
    ("ООО «Фронтир Нетворк»", "5406978329"),
]


def upgrade() -> None:
    op.create_table(
        "pstn_inn_cache_operators",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("inn", sa.Text(), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ranges_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("inn", name="uq_pstn_inn_cache_operators_inn"),
    )
    op.create_index("ix_pstn_inn_cache_operators_inn", "pstn_inn_cache_operators", ["inn"])

    op.create_table(
        "pstn_inn_ranges_cache",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("inn", sa.Text(), nullable=False),
        sa.Column("abc", sa.Text(), nullable=False),
        sa.Column("range_start", sa.Integer(), nullable=False),
        sa.Column("range_end", sa.Integer(), nullable=False),
        sa.Column("operator", sa.Text(), nullable=False),
        sa.Column("region", sa.Text(), nullable=True),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index("ix_pstn_inn_ranges_cache_inn", "pstn_inn_ranges_cache", ["inn"])
    op.create_index(
        "ix_pstn_inn_ranges_cache_abc_range",
        "pstn_inn_ranges_cache",
        ["abc", "range_start", "range_end"],
    )

    conn = op.get_bind()
    for name, inn in REQUIRED_OPERATORS:
        conn.execute(
            sa.text(
                """
                INSERT INTO pstn_inn_cache_operators
                    (id, name, inn, enabled, required, ranges_count)
                VALUES
                    (gen_random_uuid(), :name, :inn, true, true, 0)
                ON CONFLICT (inn) DO NOTHING
                """
            ),
            {"name": name, "inn": inn},
        )

    conn.execute(
        sa.text(
            """
            INSERT INTO system_settings (id, key, value, description, is_secret)
            VALUES (
                gen_random_uuid(),
                'sync_schedule',
                '{"enabled": false, "timezone": "Europe/Moscow", "hour": 21, "minute": 0}'::jsonb,
                'Daily unified sync schedule',
                false
            )
            ON CONFLICT (key) DO NOTHING
            """
        )
    )


def downgrade() -> None:
    op.drop_index("ix_pstn_inn_ranges_cache_abc_range", table_name="pstn_inn_ranges_cache")
    op.drop_index("ix_pstn_inn_ranges_cache_inn", table_name="pstn_inn_ranges_cache")
    op.drop_table("pstn_inn_ranges_cache")
    op.drop_index("ix_pstn_inn_cache_operators_inn", table_name="pstn_inn_cache_operators")
    op.drop_table("pstn_inn_cache_operators")
    op.execute(sa.text("DELETE FROM system_settings WHERE key = 'sync_schedule'"))
