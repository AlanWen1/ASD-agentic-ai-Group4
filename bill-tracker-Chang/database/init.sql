CREATE TABLE IF NOT EXISTS bills (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    amount NUMERIC(12, 2) NOT NULL CHECK (amount >= 0),
    due_date DATE NOT NULL,
    frequency VARCHAR(50) NOT NULL DEFAULT 'monthly',
    status VARCHAR(50) NOT NULL DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_bills_due_date ON bills(due_date);
CREATE INDEX idx_bills_status ON bills(status);

INSERT INTO bills (name, amount, due_date, frequency, status)
VALUES
    ('Netflix', 22.99, '2026-09-05', 'monthly', 'pending'),
    ('Electricity', 145.50, '2026-09-10', 'monthly', 'pending'),
    ('Internet', 79.99, '2026-09-15', 'monthly', 'paid')
ON CONFLICT DO NOTHING;
