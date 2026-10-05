"""Add user-scoped conversations and link legacy messages.

Revision ID: 0002_conversations
Revises: 0001_initial_schema
Create Date: 2026-10-05
"""

from alembic import op


revision = "0002_conversations"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE conversations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            user_id UUID REFERENCES users(id) ON DELETE CASCADE,
            legacy_session_id VARCHAR(100) UNIQUE,
            created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        ALTER TABLE chat_messages
        ADD COLUMN conversation_id UUID
        """
    )

    op.execute(
        """
        INSERT INTO conversations (legacy_session_id)
        SELECT DISTINCT session_id
        FROM chat_messages
        """
    )

    op.execute(
        """
        UPDATE chat_messages AS messages
        SET conversation_id = conversations.id
        FROM conversations
        WHERE conversations.legacy_session_id = messages.session_id
        """
    )

    op.execute(
        """
        ALTER TABLE chat_messages
        ALTER COLUMN conversation_id SET NOT NULL
        """
    )

    op.execute(
        """
        ALTER TABLE chat_messages
        ADD CONSTRAINT chat_messages_conversation_id_fkey
        FOREIGN KEY (conversation_id)
        REFERENCES conversations(id)
        ON DELETE CASCADE
        """
    )

    op.execute(
        "CREATE INDEX ix_conversations_user_id ON conversations (user_id)"
    )
    op.execute(
        "CREATE INDEX ix_chat_messages_conversation_id ON chat_messages (conversation_id)"
    )


def downgrade() -> None:
    op.execute(
        """
        ALTER TABLE chat_messages
        DROP CONSTRAINT IF EXISTS chat_messages_conversation_id_fkey
        """
    )
    op.execute(
        "DROP INDEX IF EXISTS ix_chat_messages_conversation_id"
    )
    op.execute(
        """
        ALTER TABLE chat_messages
        DROP COLUMN IF EXISTS conversation_id
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_conversations_user_id")
    op.execute("DROP TABLE IF EXISTS conversations")
