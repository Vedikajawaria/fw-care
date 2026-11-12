"""Add auditable reading corrections and outcome metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0002_corrections_outcomes"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def has_column(table: str, column: str) -> bool:
    return column in {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}


def upgrade() -> None:
    temperature_additions = []
    if not has_column("temperature_readings", "correction_of_id"):
        temperature_additions.append(
            sa.Column(
                "correction_of_id",
                sa.String(length=36),
                sa.ForeignKey(
                    "temperature_readings.id",
                    name="fk_temperature_correction_of",
                ),
                nullable=True,
            )
        )
    if not has_column("temperature_readings", "correction_reason"):
        temperature_additions.append(sa.Column("correction_reason", sa.Text(), nullable=False, server_default=""))
    if not has_column("temperature_readings", "recorded_at"):
        temperature_additions.append(sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=True))
    if temperature_additions:
        with op.batch_alter_table("temperature_readings") as batch_op:
            for column in temperature_additions:
                batch_op.add_column(column)
    if not has_column("temperature_readings", "recorded_at") or temperature_additions:
        op.execute("UPDATE temperature_readings SET recorded_at = measured_at WHERE recorded_at IS NULL")

    outcome_additions = []
    if not has_column("patient_outcomes", "recorded_by"):
        outcome_additions.append(
            sa.Column(
                "recorded_by",
                sa.String(length=36),
                sa.ForeignKey("users.id", name="fk_outcome_recorded_by"),
                nullable=True,
            )
        )
    if not has_column("patient_outcomes", "notes"):
        outcome_additions.append(sa.Column("notes", sa.Text(), nullable=False, server_default=""))
    if outcome_additions:
        with op.batch_alter_table("patient_outcomes") as batch_op:
            for column in outcome_additions:
                batch_op.add_column(column)
    if not has_column("patient_outcomes", "recorded_by") or outcome_additions:
        op.execute(
            "UPDATE patient_outcomes SET recorded_by = "
            "(SELECT id FROM users WHERE role = 'admin' ORDER BY username LIMIT 1) "
            "WHERE recorded_by IS NULL"
        )


def downgrade() -> None:
    for table, column in (
        ("patient_outcomes", "notes"),
        ("patient_outcomes", "recorded_by"),
        ("temperature_readings", "recorded_at"),
        ("temperature_readings", "correction_reason"),
        ("temperature_readings", "correction_of_id"),
    ):
        if has_column(table, column):
            op.drop_column(table, column)
