-- Executed by the postgres image entrypoint on first cluster init only
-- (when the pgdata volume is empty). The main database comes from
-- POSTGRES_DB; here we add the database used by the test suite.
CREATE DATABASE payments_test;
