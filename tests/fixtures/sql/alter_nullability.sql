-- make customers.email nullable
ALTER TABLE customers ALTER COLUMN email DROP NOT NULL;
