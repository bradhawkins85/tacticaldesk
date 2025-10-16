-- dialect: sqlite
ALTER TABLE organizations ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT '1970-01-01 00:00:00';
ALTER TABLE organizations ADD COLUMN updated_at TIMESTAMP NOT NULL DEFAULT '1970-01-01 00:00:00';

-- dialect: mysql
ALTER TABLE organizations
    ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP;

-- dialect: all
UPDATE organizations
SET
    created_at = CASE
        WHEN created_at IS NULL OR created_at = '1970-01-01 00:00:00' THEN CURRENT_TIMESTAMP
        ELSE created_at
    END,
    updated_at = CASE
        WHEN updated_at IS NULL OR updated_at = '1970-01-01 00:00:00' THEN CURRENT_TIMESTAMP
        ELSE updated_at
    END;
