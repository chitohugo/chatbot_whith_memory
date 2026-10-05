"""Initial database schema

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-10-04
"""

from alembic import op


revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # PostgreSQL + pgvector
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            email VARCHAR(320) NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            name VARCHAR(150) NOT NULL,
            is_active BOOLEAN NOT NULL DEFAULT TRUE
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_messages (
            id SERIAL PRIMARY KEY,
            session_id VARCHAR(100) NOT NULL,
            role VARCHAR(20) NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS agent_memories (
            id SERIAL PRIMARY KEY,
            user_id VARCHAR(100) NOT NULL,
            memory_text TEXT NOT NULL,
            embedding vector(1536),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS users")
    op.execute("DROP TABLE IF EXISTS agent_memories")
    op.execute("DROP TABLE IF EXISTS chat_messages")
    op.execute("DROP EXTENSION IF EXISTS vector")
