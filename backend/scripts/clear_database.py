from app.core.config import settings
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

DATABASE_URL = settings.database_url


def flush():
    print("\nDatabase Flush")
    print("=" * 50)
    print("\nWARNING: This is a destructive operation.")
    print("Selected tables will be DROPPED with CASCADE.")
    print("This is intended for local development only.\n")

    confirm = input("Do you want to continue? [y/N]: ").strip().lower()
    if confirm not in {"y", "yes"}:
        print("Cancelled.")
        return

    print("\nConnecting to database...")
    engine = create_engine(DATABASE_URL)

    try:
        with Session(engine) as session:
            tables = (
                session.execute(
                    text(
                        """
                    SELECT tablename
                    FROM pg_tables
                    WHERE schemaname = 'public'
                    ORDER BY tablename;
                    """
                    )
                )
                .scalars()
                .all()
            )

            if not tables:
                print("No public tables found. Nothing to do.")
                return

            print("\nAvailable tables:")
            for i, table in enumerate(tables, 1):
                print(f"  {i}. {table}")

            print("\nEnter table numbers separated by spaces, or 'all'.")
            choice = input("Selection: ").strip()

            if choice.lower() == "all":
                selected = tables
            else:
                try:
                    indexes = [int(value) for value in choice.split()]
                    if any(i < 1 or i > len(tables) for i in indexes):
                        raise ValueError
                    selected = [tables[i - 1] for i in indexes]
                except ValueError:
                    print("Invalid selection.")
                    return

            print("\nTables selected:")
            for table in selected:
                print(f"  - {table}")

            print("\nThis action cannot be easily undone.")
            confirm = input("Drop these tables? [y/N]: ").strip().lower()

            if confirm not in {"y", "yes"}:
                print("Cancelled. No changes were made.")
                return

            table_names = ", ".join(f'"{table}"' for table in selected)

            print("\nDropping tables...")

            session.execute(text(f"DROP TABLE {table_names} CASCADE"))
            session.commit()

            print(
                f"Done. Dropped {len(selected)} "
                f"table{'s' if len(selected) != 1 else ''}."
            )

    finally:
        engine.dispose()


if __name__ == "__main__":
    if "localhost" not in DATABASE_URL and "127.0.0.1" not in DATABASE_URL:
        raise RuntimeError("Refusing to flush a non-local database.")

    flush()
