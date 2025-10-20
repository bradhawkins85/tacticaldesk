-- dialect: sqlite
CREATE TABLE IF NOT EXISTS tickets (
    id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    customer TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    team TEXT NOT NULL,
    assignment TEXT NOT NULL,
    queue TEXT NOT NULL,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    channel TEXT NOT NULL DEFAULT 'Portal',
    created_at_dt TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    last_reply_dt TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    due_at_dt TIMESTAMP NULL,
    labels TEXT NOT NULL DEFAULT '[]',
    watchers TEXT NOT NULL DEFAULT '[]',
    is_starred BOOLEAN NOT NULL DEFAULT 0,
    assets_visible BOOLEAN NOT NULL DEFAULT 0,
    history TEXT NOT NULL DEFAULT '[]',
    metadata_created_at_dt TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    metadata_updated_at_dt TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
);

CREATE TABLE IF NOT EXISTS ticket_overrides (
    ticket_id TEXT PRIMARY KEY,
    subject TEXT NOT NULL,
    customer TEXT NOT NULL,
    customer_email TEXT NOT NULL,
    status TEXT NOT NULL,
    priority TEXT NOT NULL,
    team TEXT NOT NULL,
    assignment TEXT NOT NULL,
    queue TEXT NOT NULL,
    category TEXT NOT NULL,
    summary TEXT NOT NULL,
    metadata_updated_at_dt TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
);

CREATE TABLE IF NOT EXISTS ticket_replies (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ticket_id TEXT NOT NULL,
    actor TEXT NOT NULL,
    direction TEXT NOT NULL DEFAULT 'outbound',
    channel TEXT NOT NULL,
    summary TEXT NOT NULL,
    body TEXT NOT NULL,
    timestamp_dt TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
);

CREATE INDEX IF NOT EXISTS idx_ticket_replies_ticket ON ticket_replies(ticket_id);

CREATE TABLE IF NOT EXISTS ticket_deletions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL,
    value TEXT NOT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    UNIQUE(kind, value)
);

CREATE INDEX IF NOT EXISTS idx_ticket_deletions_kind ON ticket_deletions(kind);

-- dialect: mysql
CREATE TABLE IF NOT EXISTS tickets (
    id VARCHAR(32) NOT NULL PRIMARY KEY,
    subject VARCHAR(255) NOT NULL,
    customer VARCHAR(255) NOT NULL,
    customer_email VARCHAR(255) NOT NULL,
    status VARCHAR(64) NOT NULL,
    priority VARCHAR(64) NOT NULL,
    team VARCHAR(255) NOT NULL,
    assignment VARCHAR(255) NOT NULL,
    queue VARCHAR(255) NOT NULL,
    category VARCHAR(255) NOT NULL,
    summary TEXT NOT NULL,
    channel VARCHAR(64) NOT NULL DEFAULT 'Portal',
    created_at_dt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_reply_dt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    due_at_dt DATETIME NULL,
    labels JSON NOT NULL,
    watchers JSON NOT NULL,
    is_starred BOOLEAN NOT NULL DEFAULT 0,
    assets_visible BOOLEAN NOT NULL DEFAULT 0,
    history JSON NOT NULL,
    metadata_created_at_dt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_updated_at_dt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ticket_overrides (
    ticket_id VARCHAR(32) NOT NULL PRIMARY KEY,
    subject VARCHAR(255) NOT NULL,
    customer VARCHAR(255) NOT NULL,
    customer_email VARCHAR(255) NOT NULL,
    status VARCHAR(64) NOT NULL,
    priority VARCHAR(64) NOT NULL,
    team VARCHAR(255) NOT NULL,
    assignment VARCHAR(255) NOT NULL,
    queue VARCHAR(255) NOT NULL,
    category VARCHAR(255) NOT NULL,
    summary TEXT NOT NULL,
    metadata_updated_at_dt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS ticket_replies (
    id INTEGER NOT NULL PRIMARY KEY AUTO_INCREMENT,
    ticket_id VARCHAR(32) NOT NULL,
    actor VARCHAR(255) NOT NULL,
    direction VARCHAR(32) NOT NULL DEFAULT 'outbound',
    channel VARCHAR(64) NOT NULL,
    summary VARCHAR(255) NOT NULL,
    body TEXT NOT NULL,
    timestamp_dt DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE INDEX idx_ticket_replies_ticket ON ticket_replies(ticket_id);

CREATE TABLE IF NOT EXISTS ticket_deletions (
    id INTEGER NOT NULL PRIMARY KEY AUTO_INCREMENT,
    kind VARCHAR(32) NOT NULL,
    value VARCHAR(255) NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE KEY uq_ticket_deletions_kind_value (kind, value)
) ENGINE=InnoDB;

CREATE INDEX idx_ticket_deletions_kind ON ticket_deletions(kind);
