-- dialect: sqlite
CREATE TABLE IF NOT EXISTS playbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    slug TEXT NOT NULL UNIQUE,
    description TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
);
CREATE UNIQUE INDEX IF NOT EXISTS ux_playbooks_slug ON playbooks(slug);
CREATE UNIQUE INDEX IF NOT EXISTS ux_playbooks_name ON playbooks(name);

INSERT INTO playbooks (name, slug, description)
SELECT DISTINCT
    playbook,
    LOWER(
        REPLACE(
            REPLACE(
                REPLACE(
                    REPLACE(playbook, ' ', '-'),
                    '/', '-'
                ),
                '_', '-'
            ),
            '--', '-'
        )
    ),
    NULL
FROM automations
WHERE playbook IS NOT NULL
  AND playbook <> ''
  AND NOT EXISTS (
        SELECT 1 FROM playbooks WHERE playbooks.name = automations.playbook
    );

-- dialect: mysql
CREATE TABLE IF NOT EXISTS playbooks (
    id INTEGER NOT NULL PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL UNIQUE,
    slug VARCHAR(255) NOT NULL UNIQUE,
    description TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;
CREATE UNIQUE INDEX ux_playbooks_slug ON playbooks(slug);
CREATE UNIQUE INDEX ux_playbooks_name ON playbooks(name);

INSERT INTO playbooks (name, slug, description)
SELECT DISTINCT
    playbook,
    LOWER(REPLACE(REPLACE(REPLACE(REPLACE(playbook, ' ', '-'), '/', '-'), '_', '-'), '--', '-')),
    NULL
FROM automations
WHERE playbook IS NOT NULL
  AND playbook <> ''
  AND NOT EXISTS (
        SELECT 1 FROM playbooks WHERE playbooks.name = automations.playbook
    );
