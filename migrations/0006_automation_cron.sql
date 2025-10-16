-- dialect: sqlite
ALTER TABLE automations ADD COLUMN cron_expression TEXT;

-- dialect: mysql
ALTER TABLE automations ADD COLUMN cron_expression VARCHAR(255) NULL;

-- dialect: all
UPDATE automations
SET cron_expression = '0 0 * * *'
WHERE kind = 'scheduled' AND (cron_expression IS NULL OR cron_expression = '');

-- dialect: all
UPDATE automations
SET cron_expression = '0 2 * * *'
WHERE name = 'Lifecycle automation' AND kind = 'scheduled';

-- dialect: all
UPDATE automations
SET cron_expression = '0 9 1 1,4,7,10 *'
WHERE name = 'Patch window compliance' AND kind = 'scheduled';

-- dialect: all
UPDATE automations
SET cron_expression = '30 0 * * *'
WHERE name = 'Backup integrity' AND kind = 'scheduled';
