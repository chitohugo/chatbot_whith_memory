from contextlib import contextmanager
from sqlalchemy import create_engine
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker
from config import settings

# SQLAlchemy administra el pool y descarta conexiones rotas antes de usarlas.
database_url = make_url(settings.db.url).set(drivername="postgresql+psycopg2")
engine = create_engine(database_url, pool_pre_ping=True, pool_size=settings.db.pool_size, max_overflow=0, pool_timeout=5, connect_args={"connect_timeout": 5})
SessionFactory = sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def database_session():
    with SessionFactory() as session:
        try:
            yield session
        except BaseException:
            session.rollback()
            raise


def get_db_session():
    with database_session() as session:
        yield session


def close_pool():
    engine.dispose()
