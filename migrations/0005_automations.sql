-- dialect: sqlite
CREATE TABLE IF NOT EXISTS automations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    playbook TEXT NOT NULL,
    kind TEXT NOT NULL,
    cadence TEXT,
    trigger TEXT,
    status TEXT,
    next_run_at TIMESTAMP,
    last_run_at TIMESTAMP,
    last_trigger_at TIMESTAMP,
    action_label TEXT,
    action_endpoint TEXT,
    action_output_selector TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
);
CREATE INDEX IF NOT EXISTS ix_automations_kind ON automations(kind);
CREATE UNIQUE INDEX IF NOT EXISTS ux_automations_name_kind ON automations(name, kind);

-- dialect: mysql
CREATE TABLE IF NOT EXISTS automations (
    id INTEGER NOT NULL PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    description TEXT NULL,
    playbook VARCHAR(255) NOT NULL,
    kind VARCHAR(32) NOT NULL,
    cadence VARCHAR(255) NULL,
    trigger VARCHAR(255) NULL,
    status VARCHAR(64) NULL,
    next_run_at TIMESTAMP NULL,
    last_run_at TIMESTAMP NULL,
    last_trigger_at TIMESTAMP NULL,
    action_label VARCHAR(255) NULL,
    action_endpoint VARCHAR(1024) NULL,
    action_output_selector VARCHAR(255) NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY ux_automations_name_kind (name, kind),
    KEY ix_automations_kind (kind)
) ENGINE=InnoDB;

-- dialect: all
INSERT INTO automations (
    name,
    description,
    playbook,
    kind,
    cadence,
    trigger,
    status,
    next_run_at,
    last_run_at,
    last_trigger_at,
    action_label,
    action_endpoint,
    action_output_selector
)
SELECT
    'Lifecycle automation',
    'Executes the hardened update pipeline, including dependency checks and migrations.',
    'Run secure update',
    'scheduled',
    'Daily at 02:00 UTC',
    NULL,
    NULL,
    '2025-10-17 02:00:00',
    '2025-10-16 01:00:00',
    NULL,
    'Run secure update',
    '/maintenance/update',
    '#automation-update-output'
WHERE NOT EXISTS (
    SELECT 1 FROM automations WHERE name = 'Lifecycle automation' AND kind = 'scheduled'
);

-- dialect: all
INSERT INTO automations (
    name,
    description,
    playbook,
    kind,
    cadence,
    trigger,
    status,
    next_run_at,
    last_run_at,
    last_trigger_at,
    action_label,
    action_endpoint,
    action_output_selector
)
SELECT
    'Patch window compliance',
    'Generates compliance evidence and sends reports to security and audit subscribers.',
    'Quarterly patch audit',
    'scheduled',
    '1st business day of quarter',
    NULL,
    NULL,
    '2025-11-03 09:00:00',
    '2025-08-01 09:00:00',
    NULL,
    NULL,
    NULL,
    NULL
WHERE NOT EXISTS (
    SELECT 1 FROM automations WHERE name = 'Patch window compliance' AND kind = 'scheduled'
);

-- dialect: all
INSERT INTO automations (
    name,
    description,
    playbook,
    kind,
    cadence,
    trigger,
    status,
    next_run_at,
    last_run_at,
    last_trigger_at,
    action_label,
    action_endpoint,
    action_output_selector
)
SELECT
    'Backup integrity',
    'Performs checksum validation and restores a random sample to the sandbox cluster.',
    'Nightly restore validation',
    'scheduled',
    'Every night at 00:30 UTC',
    NULL,
    NULL,
    '2025-10-17 00:30:00',
    '2025-10-15 05:30:00',
    NULL,
    NULL,
    NULL,
    NULL
WHERE NOT EXISTS (
    SELECT 1 FROM automations WHERE name = 'Backup integrity' AND kind = 'scheduled'
);

-- dialect: all
INSERT INTO automations (
    name,
    description,
    playbook,
    kind,
    cadence,
    trigger,
    status,
    next_run_at,
    last_run_at,
    last_trigger_at,
    action_label,
    action_endpoint,
    action_output_selector
)
SELECT
    'Critical CVE intake',
    'Auto-creates response tickets and dispatches patch playbooks to affected fleets.',
    'Emergency patch roll-out',
    'event',
    NULL,
    'National vulnerability feed',
    'Monitoring',
    NULL,
    NULL,
    '2025-10-16 10:50:00',
    NULL,
    NULL,
    NULL
WHERE NOT EXISTS (
    SELECT 1 FROM automations WHERE name = 'Critical CVE intake' AND kind = 'event'
);

-- dialect: all
INSERT INTO automations (
    name,
    description,
    playbook,
    kind,
    cadence,
    trigger,
    status,
    next_run_at,
    last_run_at,
    last_trigger_at,
    action_label,
    action_endpoint,
    action_output_selector
)
SELECT
    'Incident escalation',
    'Notifies duty officer, syncs context to TacticalRMM, and opens on-call bridge.',
    'SOC handoff',
    'event',
    NULL,
    'Security SIEM priority 1 alert',
    'Idle',
    NULL,
    NULL,
    '2025-10-13 04:00:00',
    NULL,
    NULL,
    NULL
WHERE NOT EXISTS (
    SELECT 1 FROM automations WHERE name = 'Incident escalation' AND kind = 'event'
);

-- dialect: all
INSERT INTO automations (
    name,
    description,
    playbook,
    kind,
    cadence,
    trigger,
    status,
    next_run_at,
    last_run_at,
    last_trigger_at,
    action_label,
    action_endpoint,
    action_output_selector
)
SELECT
    'Customer onboarding',
    'Sets up portals, applies policy baselines, and delivers welcome communications.',
    'Client provisioning',
    'event',
    NULL,
    'New account webhook',
    'Healthy',
    NULL,
    NULL,
    '2025-10-09 18:00:00',
    NULL,
    NULL,
    NULL
WHERE NOT EXISTS (
    SELECT 1 FROM automations WHERE name = 'Customer onboarding' AND kind = 'event'
);
