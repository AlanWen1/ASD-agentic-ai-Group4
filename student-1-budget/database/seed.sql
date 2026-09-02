-- seed.sql
-- Budget Manager seed data — 12 budgets, 40+ categories (spec minimum: 10 per table)

DELETE FROM budget_categories;
DELETE FROM budgets;

-- ============================================
-- BUDGETS (12 records across 3 test users)
-- ============================================
INSERT INTO budgets (student_id, month, year, created_date, status) VALUES
('test01', 1, 2026, '2026-01-02 09:00:00', 'archived'),
('test01', 2, 2026, '2026-02-01 09:15:00', 'archived'),
('test01', 3, 2026, '2026-03-01 08:45:00', 'archived'),
('test01', 4, 2026, '2026-04-01 10:00:00', 'archived'),
('test01', 5, 2026, '2026-05-01 09:30:00', 'archived'),
('test01', 6, 2026, '2026-06-01 09:00:00', 'active'),
('test01', 7, 2026, '2026-07-01 09:00:00', 'active'),
('test01', 8, 2026, '2026-08-01 09:00:00', 'active'),
('test02', 6, 2026, '2026-06-02 11:00:00', 'active'),
('test02', 7, 2026, '2026-07-02 11:00:00', 'active'),
('test03', 8, 2026, '2026-08-03 14:20:00', 'active'),
('test03', 7, 2026, '2026-07-03 14:00:00', 'archived');

-- ============================================
-- BUDGET_CATEGORIES (40+ records across the 12 budgets above)
-- budget_id 1-12 correspond to insertion order above (AUTOINCREMENT starts at 1)
-- ============================================

-- budget_id 1 (test01, Jan 2026, archived) - normal, balanced
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(1, 'Rent', 1200.00, 'Monthly rent payment'),
(1, 'Groceries', 400.00, NULL),
(1, 'Utilities', 150.00, 'Electricity, water, internet'),
(1, 'Transport', 100.00, 'Public transport pass');

-- budget_id 2 (test01, Feb 2026, archived) - normal
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(2, 'Rent', 1200.00, NULL),
(2, 'Groceries', 380.00, NULL),
(2, 'Utilities', 160.00, NULL),
(2, 'Entertainment', 80.00, 'Movies and streaming');

-- budget_id 3 (test01, Mar 2026, archived) - UNREALISTIC: one category eats >70% of total
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(3, 'Rent', 1200.00, NULL),
(3, 'Gambling', 4500.00, 'Flagged: dominates the whole budget'),
(3, 'Groceries', 300.00, NULL);

-- budget_id 4 (test01, Apr 2026, archived) - UNREALISTIC: $0 for an essential category
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(4, 'Rent', 1200.00, NULL),
(4, 'Groceries', 0.00, 'Flagged: essential category set to zero'),
(4, 'Utilities', 140.00, NULL),
(4, 'Savings', 200.00, NULL);

-- budget_id 5 (test01, May 2026, archived) - normal
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(5, 'Rent', 1250.00, 'Rent increased slightly'),
(5, 'Groceries', 420.00, NULL),
(5, 'Utilities', 155.00, NULL),
(5, 'Transport', 110.00, NULL),
(5, 'Savings', 300.00, NULL);

-- budget_id 6 (test01, Jun 2026, active) - normal
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(6, 'Rent', 1250.00, NULL),
(6, 'Groceries', 410.00, NULL),
(6, 'Utilities', 150.00, NULL),
(6, 'Entertainment', 90.00, NULL);

-- budget_id 7 (test01, Jul 2026, active) - normal, more categories
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(7, 'Rent', 1250.00, NULL),
(7, 'Groceries', 400.00, NULL),
(7, 'Utilities', 145.00, NULL),
(7, 'Transport', 100.00, NULL),
(7, 'Dining Out', 150.00, NULL),
(7, 'Savings', 250.00, NULL);

-- budget_id 8 (test01, Aug 2026, active) - UNREALISTIC: one category >70%
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(8, 'Rent', 1250.00, NULL),
(8, 'Shopping', 3800.00, 'Flagged: over 70% of total budget'),
(8, 'Groceries', 350.00, NULL),
(8, 'Utilities', 140.00, NULL);

-- budget_id 9 (test02, Jun 2026, active) - normal
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(9, 'Rent', 950.00, 'Shared apartment'),
(9, 'Groceries', 300.00, NULL),
(9, 'Utilities', 100.00, NULL),
(9, 'Transport', 80.00, NULL);

-- budget_id 10 (test02, Jul 2026, active) - UNREALISTIC: $0 essential
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(10, 'Rent', 950.00, NULL),
(10, 'Groceries', 0.00, 'Flagged: essential category set to zero'),
(10, 'Subscriptions', 60.00, NULL),
(10, 'Savings', 150.00, NULL);

-- budget_id 11 (test03, Aug 2026, active) - normal
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(11, 'Rent', 1400.00, NULL),
(11, 'Groceries', 450.00, NULL),
(11, 'Utilities', 170.00, NULL),
(11, 'Transport', 120.00, NULL),
(11, 'Health', 100.00, 'Gym membership and insurance top-up');

-- budget_id 12 (test03, Jul 2026, archived) - normal
INSERT INTO budget_categories (budget_id, category_name, allocated_amount, notes) VALUES
(12, 'Rent', 1400.00, NULL),
(12, 'Groceries', 430.00, NULL),
(12, 'Utilities', 165.00, NULL),
(12, 'Entertainment', 70.00, NULL);