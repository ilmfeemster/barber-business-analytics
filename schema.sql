PRAGMA foreign_keys = ON;

CREATE TABLE clients (
    client_key TEXT PRIMARY KEY,
    groups TEXT,
    bookings_count INTEGER NOT NULL CHECK (bookings_count >= 0),
    no_shows_count INTEGER NOT NULL CHECK (no_shows_count >= 0),
    first_visit TEXT,
    last_visit TEXT,
    bookings_value REAL,
    revenue_net REAL,
    discount REAL,
    tax REAL,
    tip_amount REAL,
    total_revenue REAL
);

CREATE TABLE appointments (
    booking_id TEXT PRIMARY KEY,
    appointment_datetime TEXT NOT NULL,
    main_category TEXT,
    service TEXT NOT NULL,
    staffer TEXT,
    service_value REAL,
    addons_value REAL,
    revenue_net REAL,
    discount REAL,
    tax REAL,
    tip_amount REAL,
    total_revenue REAL,
    status TEXT NOT NULL CHECK (status IN ('Completed', 'Cancelled', 'No-show')),
    service_length_minutes INTEGER CHECK (service_length_minutes IS NULL OR service_length_minutes > 0),
    client_key TEXT,
    client_match_status TEXT NOT NULL CHECK (
        client_match_status IN ('exact_name', 'casefold_unique', 'event_date', 'ambiguous', 'unmatched')
    ),
    FOREIGN KEY (client_key) REFERENCES clients(client_key)
);

CREATE TABLE sales (
    sales_line_id INTEGER PRIMARY KEY AUTOINCREMENT,
    checkout_date TEXT NOT NULL,
    transaction_id TEXT NOT NULL,
    type TEXT,
    category TEXT,
    item TEXT,
    staffer TEXT,
    quantity REAL,
    booking_date TEXT,
    service_value REAL,
    addons_value REAL,
    revenue_net REAL,
    discount REAL,
    tax REAL,
    tip_amount REAL,
    total_revenue REAL,
    payment_type TEXT,
    client_key TEXT,
    client_match_status TEXT NOT NULL CHECK (
        client_match_status IN ('exact_name', 'casefold_unique', 'event_date', 'ambiguous', 'unmatched')
    ),
    FOREIGN KEY (client_key) REFERENCES clients(client_key)
);

CREATE INDEX idx_appointments_datetime ON appointments(appointment_datetime);
CREATE INDEX idx_appointments_status ON appointments(status);
CREATE INDEX idx_appointments_client_key ON appointments(client_key);
CREATE INDEX idx_sales_checkout_date ON sales(checkout_date);
CREATE INDEX idx_sales_transaction_id ON sales(transaction_id);
CREATE INDEX idx_sales_client_key ON sales(client_key);
