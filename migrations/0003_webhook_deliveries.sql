-- dialect: sqlite
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id TEXT NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'retrying',
    last_attempt_at TIMESTAMP NULL,
    next_retry_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
);
-- dialect: mysql
CREATE TABLE IF NOT EXISTS webhook_deliveries (
    id INTEGER NOT NULL PRIMARY KEY AUTO_INCREMENT,
    event_id VARCHAR(128) NOT NULL UNIQUE,
    endpoint TEXT NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'retrying',
    last_attempt_at TIMESTAMP NULL,
    next_retry_at TIMESTAMP NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;
