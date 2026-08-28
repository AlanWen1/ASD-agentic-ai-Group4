INSERT INTO budgets (student_id, month, year, created_date, status)
VALUES
    ('test01', 8, 2026, '2026-08-01 09:00:00', 'active'),
    ('test02', 9, 2026, '2026-08-24 20:15:00', 'active');

INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes)
VALUES
    (1, 'Groceries', 400.00, 'Weekly shop average based on last 3 months'),
    (1, 'Transport', 120.00, 'Opal card top-ups + occasional rideshare');