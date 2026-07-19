ALTER TABLE IF EXISTS users
    DROP CONSTRAINT IF EXISTS ck_users_login_id_format;

ALTER TABLE IF EXISTS users
    ALTER COLUMN login_id TYPE VARCHAR(255);

ALTER INDEX IF EXISTS uq_users_login_id_active
    RENAME TO uq_users_email_active;

ALTER TABLE IF EXISTS users
    RENAME COLUMN login_id TO email;
