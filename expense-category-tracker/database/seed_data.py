"""
Populates the categories and expenses tables with sample data so each
table meets the assignment's "minimum 10 records" requirement.

All seed rows are attached to DEMO_USER_ID since every row now belongs
to a specific user (see database.py) — this just gives the first/demo
account something to look at, it doesn't seed data for every user.

Run with:  python seed_data.py
"""
from database import get_db, init_db
from datetime import date, timedelta
import random

init_db()

DEMO_USER_ID = 1

CATEGORIES = [
    ("Groceries", "Essential"),
    ("Dining", "Discretionary"),
    ("Transport", "Essential"),
    ("Utilities", "Essential"),
    ("Entertainment", "Discretionary"),
    ("Shopping", "Discretionary"),
    ("Health", "Essential"),
    ("Travel", "Discretionary"),
    ("Education", "Essential"),
    ("Other", "Discretionary"),
]

EXPENSES = [
    (85.40, "Weekly grocery shop", "Woolworths", "Groceries"),
    (12.50, "Coffee with a friend", "Corner Cafe", "Dining"),
    (45.00, "Petrol fill-up", "Shell", "Transport"),
    (120.00, "Electricity bill", "AGL", "Utilities"),
    (35.99, "Movie tickets", "Event Cinemas", "Entertainment"),
    (89.90, "New headphones", "JB Hi-Fi", "Shopping"),
    (60.00, "Pharmacy items", "Chemist Warehouse", "Health"),
    (22.30, "Lunch with colleagues", "Subway", "Dining"),
    (15.00, "Bus tickets", "Opal", "Transport"),
    (150.00, "Internet bill", "Telstra", "Utilities"),
    (40.00, "Gym membership top-up", "Anytime Fitness", "Health"),
    (18.75, "Snacks and drinks", "7-Eleven", "Other"),
]


def run():
    conn = get_db()
    cur = conn.cursor()

    for name, ctype in CATEGORIES:
        cur.execute(
            "INSERT OR IGNORE INTO categories (user_id, name, type) VALUES (?, ?, ?)",
            (DEMO_USER_ID, name, ctype),
        )
    conn.commit()

    cat_ids = {
        row["name"]: row["id"]
        for row in cur.execute(
            "SELECT id, name FROM categories WHERE user_id = ?", (DEMO_USER_ID,)
        ).fetchall()
    }

    today = date.today()
    for amount, desc, merchant, cat_name in EXPENSES:
        expense_date = (today - timedelta(days=random.randint(0, 30))).isoformat()
        cur.execute(
            "INSERT INTO expenses (user_id, amount, description, merchant, category_id, date) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (DEMO_USER_ID, amount, desc, merchant, cat_ids.get(cat_name), expense_date),
        )
    conn.commit()
    conn.close()
    print(f"Seeded {len(CATEGORIES)} categories and {len(EXPENSES)} expenses.")


if __name__ == "__main__":
    run()
