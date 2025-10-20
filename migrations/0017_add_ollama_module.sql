-- dialect: sqlite
CREATE TABLE IF NOT EXISTS ticket_summaries (
    ticket_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL DEFAULT 'ollama',
    model TEXT,
    summary TEXT,
    error_message TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
);

-- dialect: mysql
CREATE TABLE IF NOT EXISTS ticket_summaries (
    ticket_id VARCHAR(32) NOT NULL PRIMARY KEY,
    provider VARCHAR(64) NOT NULL DEFAULT 'ollama',
    model VARCHAR(255) NULL,
    summary TEXT NULL,
    error_message TEXT NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

-- dialect: all
INSERT INTO integration_modules (name, slug, description, icon, enabled, settings)
SELECT
    'Ollama',
    'ollama',
    'Local AI assistant that summarises ticket context and powers generative workflows.',
    '🧠',
    0,
    '{"base_url": "http://127.0.0.1:11434", "model": "llama3", "prompt": ""}'
WHERE NOT EXISTS (SELECT 1 FROM integration_modules WHERE slug = 'ollama');
