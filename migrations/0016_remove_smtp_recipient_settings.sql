-- dialect: sqlite
UPDATE integration_modules
SET settings = json_remove(json_remove(settings, '$.smtp_recipients'), '$.smtp_cc')
WHERE slug = 'smtp-email';

-- dialect: mysql
UPDATE integration_modules
SET settings = JSON_REMOVE(JSON_REMOVE(settings, '$.smtp_recipients'), '$.smtp_cc')
WHERE slug = 'smtp-email';

-- dialect: postgresql
UPDATE integration_modules
SET settings = settings - 'smtp_recipients' - 'smtp_cc'
WHERE slug = 'smtp-email';
