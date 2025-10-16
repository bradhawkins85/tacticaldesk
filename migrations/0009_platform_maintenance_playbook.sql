-- dialect: all
UPDATE automations
SET playbook = 'Platform maintenance'
WHERE name = 'Lifecycle automation' AND playbook = 'Run secure update';

UPDATE playbooks
SET
    name = 'Platform maintenance',
    slug = 'platform-maintenance'
WHERE name = 'Run secure update';
