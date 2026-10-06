"""ORM runtime, reviewed file actions, pagination indexes and timezone dates."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column
from uuid import UUID

revision = "0003_runtime_and_management"
down_revision = "0002_conversations"
branch_labels = None
depends_on = None


class MigrationBase(DeclarativeBase):
    pass


class MigrationConversation(MigrationBase):
    __tablename__ = "conversations"
    id: Mapped[UUID] = mapped_column(sa.Uuid, primary_key=True)
    title: Mapped[str | None] = mapped_column(sa.String(120))


class MigrationMessage(MigrationBase):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    conversation_id: Mapped[UUID] = mapped_column(sa.Uuid)
    role: Mapped[str] = mapped_column(sa.String(20))
    content: Mapped[str] = mapped_column(sa.Text)


def upgrade():
    op.add_column("conversations", sa.Column("title", sa.String(120)))
    op.add_column("conversations", sa.Column("archived", sa.Boolean, nullable=False, server_default=sa.false()))
    for table, columns in {"conversations": ("created_at", "updated_at"), "chat_messages": ("created_at",), "agent_memories": ("created_at",)}.items():
        for name in columns:
            # Conversión de esquema: los timestamps legacy se interpretaban UTC.
            op.alter_column(table, name, type_=sa.DateTime(timezone=True), postgresql_using=f"{name} AT TIME ZONE 'UTC'")
    op.create_index("ix_conversations_owner_activity", "conversations", ["user_id", "updated_at", "id"])
    op.create_index("ix_messages_conversation_order", "chat_messages", ["conversation_id", "id"])
    op.create_index("ix_agent_memories_user_id", "agent_memories", ["user_id"])
    op.create_table("chat_runs",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("conversation_id", sa.Uuid, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("request_id", sa.Uuid, nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("transcript", sa.JSON, nullable=False),
        sa.Column("metrics", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)))
    op.create_index("ix_chat_runs_conversation_id", "chat_runs", ["conversation_id"])
    op.create_table("tool_executions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("run_id", sa.Uuid, sa.ForeignKey("chat_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("call_id", sa.String(200), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("arguments", sa.JSON, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("duration_ms", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "call_id"))
    op.create_index("ix_tool_executions_run_id", "tool_executions", ["run_id"])
    op.create_table("tool_actions",
        sa.Column("id", sa.Uuid, primary_key=True),
        sa.Column("conversation_id", sa.Uuid, sa.ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("run_id", sa.Uuid, sa.ForeignKey("chat_runs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("arguments", sa.JSON, nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("preview", sa.JSON, nullable=False),
        sa.Column("result", sa.JSON, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("run_id", "fingerprint"))
    op.create_index("ix_tool_actions_conversation_id", "tool_actions", ["conversation_id"])
    op.create_table("login_attempts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("key", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False))
    op.create_index("ix_login_attempts_key", "login_attempts", ["key"])
    op.create_index("ix_login_attempts_created_at", "login_attempts", ["created_at"])
    # Backfill con objetos ORM versionados, sin inferir propietarios legacy.
    session = Session(bind=op.get_bind())
    for conversation in session.scalars(sa.select(MigrationConversation)):
        first = session.scalar(sa.select(MigrationMessage).where(MigrationMessage.conversation_id == conversation.id, MigrationMessage.role == "user").order_by(MigrationMessage.id).limit(1))
        if first:
            conversation.title = " ".join(first.content.split())[:120]
    session.flush()


def downgrade():
    for table in ("login_attempts", "tool_actions", "tool_executions", "chat_runs"):
        op.drop_table(table)
    op.drop_index("ix_agent_memories_user_id", table_name="agent_memories")
    op.drop_index("ix_messages_conversation_order", table_name="chat_messages")
    op.drop_index("ix_conversations_owner_activity", table_name="conversations")
    op.drop_column("conversations", "archived")
    op.drop_column("conversations", "title")
    for table, columns in {"conversations": ("created_at", "updated_at"), "chat_messages": ("created_at",), "agent_memories": ("created_at",)}.items():
        for name in columns:
            op.alter_column(table, name, type_=sa.DateTime(timezone=False), postgresql_using=f"{name} AT TIME ZONE 'UTC'")
