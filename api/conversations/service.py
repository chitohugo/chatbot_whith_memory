from uuid import UUID


_CONVERSATION_COLUMNS = """
    id,
    user_id,
    legacy_session_id,
    created_at,
    updated_at
"""

_MESSAGE_COLUMNS = """
    id,
    conversation_id,
    role,
    content,
    created_at
"""


def create_conversation(db, user_id: UUID):
    with db.cursor() as cursor:
        cursor.execute(
            f"""
            INSERT INTO conversations (user_id)
            VALUES (%s)
            RETURNING {_CONVERSATION_COLUMNS}
            """,
            (str(user_id),),
        )
        conversation = cursor.fetchone()

    db.commit()
    return conversation


def list_conversations(db, user_id: UUID):
    with db.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {_CONVERSATION_COLUMNS}
            FROM conversations
            WHERE user_id = %s
            ORDER BY updated_at DESC, created_at DESC
            """,
            (str(user_id),),
        )
        return cursor.fetchall()


def get_conversation(db, conversation_id: UUID, user_id: UUID):
    with db.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {_CONVERSATION_COLUMNS}
            FROM conversations
            WHERE id = %s AND user_id = %s
            """,
            (str(conversation_id), str(user_id)),
        )
        return cursor.fetchone()


def list_messages(db, conversation_id: UUID, user_id: UUID):
    with db.cursor() as cursor:
        cursor.execute(
            f"""
            SELECT {_MESSAGE_COLUMNS}
            FROM chat_messages AS messages
            INNER JOIN conversations
                ON conversations.id = messages.conversation_id
            WHERE messages.conversation_id = %s
              AND conversations.user_id = %s
            ORDER BY messages.created_at ASC, messages.id ASC
            """,
            (str(conversation_id), str(user_id)),
        )
        return cursor.fetchall()


def create_message(db, conversation_id: UUID, user_id: UUID, role: str, content: str):
    with db.cursor() as cursor:
        cursor.execute(
            """
            INSERT INTO chat_messages (conversation_id, session_id, role, content)
            SELECT %s, COALESCE(legacy_session_id, id::text), %s, %s
            FROM conversations
            WHERE id = %s AND user_id = %s
            RETURNING id, conversation_id, role, content, created_at
            """,
            (
                str(conversation_id),
                role,
                content,
                str(conversation_id),
                str(user_id),
            ),
        )
        message = cursor.fetchone()

        if message:
            cursor.execute(
                """
                UPDATE conversations
                SET updated_at = CURRENT_TIMESTAMP
                WHERE id = %s AND user_id = %s
                """,
                (str(conversation_id), str(user_id)),
            )

    db.commit()
    return message


def delete_conversation(db, conversation_id: UUID, user_id: UUID) -> bool:
    with db.cursor() as cursor:
        cursor.execute(
            """
            DELETE FROM conversations
            WHERE id = %s AND user_id = %s
            RETURNING id
            """,
            (str(conversation_id), str(user_id)),
        )
        deleted = cursor.fetchone()

    db.commit()
    return deleted is not None
