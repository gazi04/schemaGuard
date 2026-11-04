-- rename orders.status to state
ALTER TABLE orders RENAME COLUMN status TO state;
