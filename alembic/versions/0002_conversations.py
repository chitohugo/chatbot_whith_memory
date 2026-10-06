"""Add user-scoped conversations and link legacy messages."""
from uuid import UUID, uuid4
from alembic import op
import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

revision = "0002_conversations"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


class MigrationBase(DeclarativeBase):
    pass


class LegacyConversation(MigrationBase):
    __tablename__ = "conversations"
    id: Mapped[UUID] = mapped_column(sa.Uuid, primary_key=True, default=uuid4)
    legacy_session_id: Mapped[str] = mapped_column(sa.String(100))


class LegacyMessage(MigrationBase):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(sa.Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(sa.String(100))
    conversation_id: Mapped[UUID | None] = mapped_column(sa.Uuid)


def upgrade():
    op.create_table("conversations",
        sa.Column("id", sa.Uuid, primary_key=True, server_default=sa.func.gen_random_uuid()),
        sa.Column("user_id", sa.Uuid, sa.ForeignKey("users.id", ondelete="CASCADE")),
        sa.Column("legacy_session_id", sa.String(100), unique=True),
        sa.Column("created_at", sa.DateTime, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime, nullable=False, server_default=sa.func.now()))
    op.add_column("chat_messages", sa.Column("conversation_id", sa.Uuid))
    session = Session(bind=op.get_bind())
    conversations = {}
    for message in session.scalars(sa.select(LegacyMessage).order_by(LegacyMessage.id)):
        if message.session_id not in conversations:
            conversation = LegacyConversation(legacy_session_id=message.session_id)
            session.add(conversation)
            session.flush()
            conversations[message.session_id] = conversation.id
        message.conversation_id = conversations[message.session_id]
    session.flush()
    op.alter_column("chat_messages", "conversation_id", nullable=False)
    op.create_foreign_key("chat_messages_conversation_id_fkey", "chat_messages", "conversations", ["conversation_id"], ["id"], ondelete="CASCADE")
    op.create_index("ix_conversations_user_id", "conversations", ["user_id"])
    op.create_index("ix_chat_messages_conversation_id", "chat_messages", ["conversation_id"])


def downgrade():
    op.drop_constraint("chat_messages_conversation_id_fkey", "chat_messages", type_="foreignkey")
    op.drop_index("ix_chat_messages_conversation_id", table_name="chat_messages")
    op.drop_column("chat_messages", "conversation_id")
    op.drop_index("ix_conversations_user_id", table_name="conversations")
    op.drop_table("conversations")
