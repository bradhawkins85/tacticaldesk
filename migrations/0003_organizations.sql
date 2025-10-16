-- dialect: sqlite
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    contact_email TEXT,
    is_archived INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
);

CREATE INDEX IF NOT EXISTS idx_organizations_status ON organizations(is_archived);

-- dialect: mysql
CREATE TABLE IF NOT EXISTS organizations (
    id INTEGER NOT NULL PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    description TEXT NULL,
    contact_email VARCHAR(255) NULL,
    is_archived BOOLEAN NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE INDEX idx_organizations_status ON organizations (is_archived);

-- dialect: all
INSERT INTO organizations (name, slug, description, contact_email, is_archived)
SELECT
    'Quest Logistics',
    'quest-logistics',
    'Global supply chain operator with managed warehouse technology footprint.',
    'ops@questlogistics.example',
    0
WHERE NOT EXISTS (SELECT 1 FROM organizations WHERE slug = 'quest-logistics');

-- dialect: all
INSERT INTO organizations (name, slug, description, contact_email, is_archived)
SELECT
    'Northwind Retail',
    'northwind-retail',
    'Regional retail partner piloting Tactical Desk for frontline support.',
    'service@northwindretail.example',
    0
WHERE NOT EXISTS (SELECT 1 FROM organizations WHERE slug = 'northwind-retail');
