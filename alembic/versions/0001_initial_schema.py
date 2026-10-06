"""Initial database schema."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.types import UserDefinedType

revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


class Vector1536(UserDefinedType):
    def get_col_spec(self, **kwargs):
        return "vector(1536)"


def upgrade():
    op.execute(sa.schema.DDL("CREATE EXTENSION IF NOT EXISTS vector"))
    op.create_table("users",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text, nullable=False),
        sa.Column("name", sa.String(150), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()))
    op.create_table("chat_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("session_id", sa.String(100), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()))
    op.create_table("agent_memories",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.String(100), nullable=False),
        sa.Column("memory_text", sa.Text, nullable=False),
        sa.Column("embedding", Vector1536()),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()))


def downgrade():
    for table in ("agent_memories", "chat_messages", "users"):
        op.drop_table(table)
    op.execute(sa.schema.DDL("DROP EXTENSION IF EXISTS vector"))
