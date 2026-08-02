"""indexes for catalog facet/filter columns

Revision ID: 0007_facet_indexes
Revises: 0006_purchased_extras
Create Date: 2026-08-02
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0007_facet_indexes"
down_revision: Union[str, None] = "0006_purchased_extras"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(
        "ix_catalog_kind_present_msisdn",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "msisdn"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_region",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "region_name"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_city",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "city_name"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_status",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "status_raw"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_mask",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "mask"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_number_type",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "number_type"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_operator_fas",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "operator_fas"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_provider",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "provider_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_order_id",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "order_id"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_class",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "class"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_operator",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "operator"],
        unique=False,
    )
    op.create_index(
        "ix_catalog_kind_present_partner",
        "numbers_catalog_normalized",
        ["inventory_kind", "is_currently_present", "partner"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_catalog_kind_present_partner", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_operator", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_class", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_order_id", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_provider", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_operator_fas", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_number_type", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_mask", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_status", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_city", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_region", table_name="numbers_catalog_normalized")
    op.drop_index("ix_catalog_kind_present_msisdn", table_name="numbers_catalog_normalized")
