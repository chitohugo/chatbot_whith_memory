import psycopg2

from config import settings


def get_db_connection():
    connection = psycopg2.connect(
        settings.db.url
    )

    try:
        yield connection
    finally:
        connection.close()