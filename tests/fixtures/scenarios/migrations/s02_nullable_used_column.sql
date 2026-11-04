-- make customers.name nullable
ALTER TABLE customers ALTER COLUMN name DROP NOT NULL;
