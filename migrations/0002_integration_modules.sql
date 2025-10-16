-- dialect: sqlite
CREATE TABLE IF NOT EXISTS integration_modules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    icon TEXT,
    enabled INTEGER NOT NULL DEFAULT 0,
    settings TEXT NOT NULL DEFAULT '{}',
    created_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
);

-- dialect: mysql
CREATE TABLE IF NOT EXISTS integration_modules (
    id INTEGER NOT NULL PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    description TEXT NULL,
    icon VARCHAR(32) NULL,
    enabled BOOLEAN NOT NULL DEFAULT 0,
    settings JSON NOT NULL DEFAULT (JSON_OBJECT()),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- dialect: all
INSERT INTO integration_modules (name, slug, description, icon, enabled, settings)
SELECT
    'SyncroRMM',
    'syncro-rmm',
    'SyncroRMM automation and ticket synchronization.',
    '🛠️',
    1,
    '{"base_url": "", "api_key": "", "webhook_url": ""}'
WHERE NOT EXISTS (SELECT 1 FROM integration_modules WHERE slug = 'syncro-rmm');

-- dialect: all
INSERT INTO integration_modules (name, slug, description, icon, enabled, settings)
SELECT
    'TacticalRMM',
    'tactical-rmm',
    'TacticalRMM device telemetry ingestion and automation hooks.',
    '🛰️',
    1,
    '{"base_url": "", "api_key": "", "webhook_url": ""}'
WHERE NOT EXISTS (SELECT 1 FROM integration_modules WHERE slug = 'tactical-rmm');

-- dialect: all
INSERT INTO integration_modules (name, slug, description, icon, enabled, settings)
SELECT
    'Xero',
    'xero',
    'Xero accounting integration for financial automation.',
    '💼',
    0,
    '{"base_url": "", "client_id": "", "client_secret": "", "tenant_id": ""}'
WHERE NOT EXISTS (SELECT 1 FROM integration_modules WHERE slug = 'xero');
