PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS budgets (
    budget_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id    TEXT NOT NULL,
    month         INTEGER NOT NULL CHECK (month BETWEEN 1 AND 12),
    year          INTEGER NOT NULL,
    created_date  TEXT NOT NULL DEFAULT (datetime('now')),
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'archived'))
);

CREATE TABLE IF NOT EXISTS budget_categories (
    category_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    budget_id          INTEGER NOT NULL,
    category_name      TEXT NOT NULL,
    allocated_amount   REAL NOT NULL CHECK (allocated_amount >= 0),
    notes              TEXT,
    FOREIGN KEY (budget_id) REFERENCES budgets(budget_id) ON DELETE CASCADE
);