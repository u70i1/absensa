from app.core.config import settings
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = settings.database_url
# or:
# DATABASE_URL = settings.test_database_url


def flush():
    """Deletes ALL data in the database, except alembic_version table"""
    confirm = input(
        "Whoa! You're about to use a destructive feature.\nThis is intended for development only. Continue? (Y/n): "
    )

    if confirm.lower() != "y":
        print("Canceling operation...")
        return

    print("Connecting to the database...")
    engine = create_engine(DATABASE_URL)

    try:
        with Session(engine) as session:
            tables = (
                session.execute(
                    text("""
                    SELECT tablename
                    FROM pg_tables
                        WHERE schemaname = 'public'
                        AND tablename <> 'alembic_version'
                        ORDER BY tablename;
                """)
                )
                .scalars()
                .all()
            )

            if not tables:
                print("Nothing to truncate.")
                return

            table_name = ", ".join(f'"{table}"' for table in tables)

            print("Deleting table contents... ", end="")
            session.execute(
                text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE")
            )
            print("Done")

            session.commit()
    finally:
        engine.dispose()


if __name__ == "__main__":
    if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
        raise RuntimeError("Refusing to flush a non-local database.")

    flush()
