-- several changes in one transaction
BEGIN;

ALTER TABLE orders ADD COLUMN coupon_code TEXT;
ALTER TABLE customers ALTER COLUMN notes TYPE TEXT;
DROP TABLE payments;

COMMIT;
