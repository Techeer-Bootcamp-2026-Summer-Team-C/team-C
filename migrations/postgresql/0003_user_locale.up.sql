ALTER TABLE users
    ADD COLUMN locale VARCHAR(2) NOT NULL DEFAULT 'EN';

ALTER TABLE users
    ADD CONSTRAINT ck_users_locale
    CHECK (locale IN ('EN', 'KO'));
