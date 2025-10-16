-- dialect: sqlite
ALTER TABLE automations ADD COLUMN ticket_actions TEXT;

-- dialect: mysql
ALTER TABLE automations ADD COLUMN ticket_actions JSON NULL;
