import sqlite3
import os

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "budget_manager.db")
SCHEMA_PATH = os.path.join(DB_DIR, "schema.sql")
SEED_PATH = os.path.join(DB_DIR, "seed.sql")


def init_db(reset: bool = True) -> None:
    if reset and os.path.exists(DB_PATH):
        os.remove(DB_PATH)
        print(f"Removed existing database at {DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")

    with open(SCHEMA_PATH, "r") as f:
        conn.executescript(f.read())
    print("Schema applied: budgets, budget_categories")

    with open(SEED_PATH, "r") as f:
        conn.executescript(f.read())
    print("Seed data inserted (2 test records per table)")

    conn.commit()

    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM budgets")
    budget_count = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM budget_categories")
    category_count = cur.fetchone()[0]
    print(f"budgets: {budget_count} rows | budget_categories: {category_count} rows")

    conn.close()
    print(f"Database ready at {DB_PATH}")


if __name__ == "__main__":
    init_db()
