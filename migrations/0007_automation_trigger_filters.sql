-- dialect: sqlite
ALTER TABLE automations ADD COLUMN trigger_filters TEXT;

-- dialect: mysql
ALTER TABLE automations ADD COLUMN trigger_filters JSON NULL;
