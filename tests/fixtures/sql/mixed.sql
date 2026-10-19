-- realistic migration: changes wrapped in a transaction
BEGIN;

ALTER TABLE customers DROP COLUMN signup_date;
ALTER TABLE orders RENAME COLUMN amount TO total;

COMMIT;
