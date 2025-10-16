-- 0010_remove_playbooks.sql
-- Merge playbook descriptions into automations and drop the legacy playbooks table.

UPDATE automations
SET description = (
        SELECT description
        FROM playbooks
        WHERE playbooks.name = automations.playbook
    )
WHERE (description IS NULL OR trim(description) = '')
  AND EXISTS (
        SELECT 1
        FROM playbooks
        WHERE playbooks.name = automations.playbook
          AND playbooks.description IS NOT NULL
          AND trim(playbooks.description) != ''
    );

DROP TABLE IF EXISTS playbooks;
