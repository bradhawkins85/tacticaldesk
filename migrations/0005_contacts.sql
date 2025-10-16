-- dialect: sqlite
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id INTEGER NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
    name TEXT NOT NULL,
    job_title TEXT,
    email TEXT,
    phone TEXT,
    notes TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
);

CREATE INDEX IF NOT EXISTS idx_contacts_organization ON contacts(organization_id);

-- dialect: mysql
CREATE TABLE IF NOT EXISTS contacts (
    id INTEGER NOT NULL PRIMARY KEY AUTO_INCREMENT,
    organization_id INTEGER NOT NULL,
    name VARCHAR(255) NOT NULL,
    job_title VARCHAR(255) NULL,
    email VARCHAR(255) NULL,
    phone VARCHAR(64) NULL,
    notes TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    CONSTRAINT fk_contacts_organization
        FOREIGN KEY (organization_id) REFERENCES organizations(id)
        ON DELETE CASCADE
) ENGINE=InnoDB;

CREATE INDEX idx_contacts_organization ON contacts (organization_id);

-- dialect: all
INSERT INTO contacts (organization_id, name, job_title, email, phone, notes)
SELECT
    org.id,
    'Alicia Patel',
    'IT Service Manager',
    'alicia.patel@questlogistics.example',
    '+1-415-555-0148',
    'Primary escalation contact coordinating VPN remediation efforts.'
FROM organizations AS org
WHERE org.slug = 'quest-logistics'
  AND NOT EXISTS (
        SELECT 1 FROM contacts WHERE organization_id = org.id AND name = 'Alicia Patel'
    );

-- dialect: all
INSERT INTO contacts (organization_id, name, job_title, email, phone, notes)
SELECT
    org.id,
    'Maria Gomez',
    'Operations Lead',
    'maria.gomez@northwindretail.example',
    '+1-206-555-0199',
    'Coordinates onboarding and fulfilment service tickets.'
FROM organizations AS org
WHERE org.slug = 'northwind-retail'
  AND NOT EXISTS (
        SELECT 1 FROM contacts WHERE organization_id = org.id AND name = 'Maria Gomez'
    );
