UPDATE users
SET email = LOWER(BTRIM(email));

ALTER TABLE users
    RENAME COLUMN email TO login_id;

ALTER TABLE users
    ALTER COLUMN login_id TYPE VARCHAR(64);

ALTER INDEX uq_users_email_active
    RENAME TO uq_users_login_id_active;

ALTER TABLE users
    ADD CONSTRAINT ck_users_login_id_format
    CHECK (
        login_id = LOWER(BTRIM(login_id))
        AND login_id ~ '^[a-z0-9][a-z0-9._@+-]{2,63}$'
    );
