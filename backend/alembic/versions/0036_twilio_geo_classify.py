"""Twilio raw geo columns and geo unique that includes region

Revision ID: 0036_twilio_geo_classify
Revises: 0035_catalog_client
Create Date: 2026-08-27
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0036_twilio_geo_classify"
down_revision: Union[str, None] = "0035_catalog_client"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("twilio_available_numbers", sa.Column("region_raw", sa.Text(), nullable=True))
    op.add_column("twilio_available_numbers", sa.Column("locality_raw", sa.Text(), nullable=True))
    op.execute(
        """
        UPDATE twilio_available_numbers
        SET region_raw = region,
            locality_raw = locality
        WHERE region_raw IS NULL AND locality_raw IS NULL
        """
    )

    op.add_column(
        "twilio_geo",
        sa.Column("region_norm", sa.Text(), nullable=False, server_default=""),
    )
    op.execute(
        """
        UPDATE twilio_geo
        SET region_norm = lower(btrim(coalesce(region, '')))
        """
    )
    op.execute(
        """
        DELETE FROM twilio_geo g
        USING twilio_geo keep
        WHERE g.provider_id = keep.provider_id
          AND g.country_iso = keep.country_iso
          AND g.number_type = keep.number_type
          AND g.region_filter = keep.region_filter
          AND g.region_norm = keep.region_norm
          AND g.locality_norm = keep.locality_norm
          AND g.id > keep.id
        """
    )
    op.drop_constraint("uq_twilio_geo_cell", "twilio_geo", type_="unique")
    op.create_unique_constraint(
        "uq_twilio_geo_cell",
        "twilio_geo",
        [
            "provider_id",
            "country_iso",
            "number_type",
            "region_filter",
            "region_norm",
            "locality_norm",
        ],
    )


def downgrade() -> None:
    op.drop_constraint("uq_twilio_geo_cell", "twilio_geo", type_="unique")
    op.create_unique_constraint(
        "uq_twilio_geo_cell",
        "twilio_geo",
        ["provider_id", "country_iso", "number_type", "region_filter", "locality_norm"],
    )
    op.drop_column("twilio_geo", "region_norm")
    op.drop_column("twilio_available_numbers", "locality_raw")
    op.drop_column("twilio_available_numbers", "region_raw")
