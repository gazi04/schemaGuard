-- rename customers.signup_date to created_at
ALTER TABLE customers RENAME COLUMN signup_date TO created_at;
