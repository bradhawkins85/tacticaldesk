-- dialect: sqlite
CREATE TABLE IF NOT EXISTS knowledge_spaces (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    slug TEXT NOT NULL UNIQUE,
    description TEXT,
    icon TEXT,
    is_private INTEGER NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now'))
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    space_id INTEGER NOT NULL,
    parent_id INTEGER,
    title TEXT NOT NULL,
    slug TEXT NOT NULL,
    summary TEXT,
    content TEXT NOT NULL,
    is_published INTEGER NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_by_id INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    updated_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    published_at TIMESTAMP,
    CONSTRAINT fk_knowledge_documents_space FOREIGN KEY (space_id) REFERENCES knowledge_spaces(id) ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_documents_parent FOREIGN KEY (parent_id) REFERENCES knowledge_documents(id) ON DELETE SET NULL,
    CONSTRAINT fk_knowledge_documents_user FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT uq_knowledge_documents_space_slug UNIQUE (space_id, slug)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_documents_space_id ON knowledge_documents(space_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_parent_id ON knowledge_documents(parent_id);
CREATE INDEX IF NOT EXISTS ix_knowledge_documents_created_by_id ON knowledge_documents(created_by_id);

CREATE TABLE IF NOT EXISTS knowledge_document_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    title TEXT NOT NULL,
    summary TEXT,
    content TEXT NOT NULL,
    created_by_id INTEGER,
    created_at TIMESTAMP NOT NULL DEFAULT (DATETIME('now')),
    CONSTRAINT fk_knowledge_document_revisions_document FOREIGN KEY (document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_knowledge_document_revisions_user FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT uq_knowledge_revision_document_version UNIQUE (document_id, version)
);

CREATE INDEX IF NOT EXISTS ix_knowledge_document_revisions_document_id ON knowledge_document_revisions(document_id);

-- dialect: mysql
CREATE TABLE IF NOT EXISTS knowledge_spaces (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    description TEXT NULL,
    icon VARCHAR(16) NULL,
    is_private TINYINT(1) NOT NULL DEFAULT 0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
) ENGINE=InnoDB;

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    space_id INTEGER NOT NULL,
    parent_id INTEGER NULL,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    summary TEXT NULL,
    content LONGTEXT NOT NULL,
    is_published TINYINT(1) NOT NULL DEFAULT 0,
    position INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_by_id INTEGER NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    published_at TIMESTAMP NULL,
    CONSTRAINT fk_kd_space FOREIGN KEY (space_id) REFERENCES knowledge_spaces(id) ON DELETE CASCADE,
    CONSTRAINT fk_kd_parent FOREIGN KEY (parent_id) REFERENCES knowledge_documents(id) ON DELETE SET NULL,
    CONSTRAINT fk_kd_user FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT uq_kd_space_slug UNIQUE (space_id, slug)
) ENGINE=InnoDB;

CREATE INDEX IF NOT EXISTS ix_kd_space_id ON knowledge_documents(space_id);
CREATE INDEX IF NOT EXISTS ix_kd_parent_id ON knowledge_documents(parent_id);
CREATE INDEX IF NOT EXISTS ix_kd_created_by_id ON knowledge_documents(created_by_id);

CREATE TABLE IF NOT EXISTS knowledge_document_revisions (
    id INTEGER PRIMARY KEY AUTO_INCREMENT,
    document_id INTEGER NOT NULL,
    version INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary TEXT NULL,
    content LONGTEXT NOT NULL,
    created_by_id INTEGER NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT fk_kdr_document FOREIGN KEY (document_id) REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    CONSTRAINT fk_kdr_user FOREIGN KEY (created_by_id) REFERENCES users(id) ON DELETE SET NULL,
    CONSTRAINT uq_kdr_document_version UNIQUE (document_id, version)
) ENGINE=InnoDB;

CREATE INDEX IF NOT EXISTS ix_kdr_document_id ON knowledge_document_revisions(document_id);

-- dialect: postgresql
CREATE TABLE IF NOT EXISTS knowledge_spaces (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL UNIQUE,
    description TEXT NULL,
    icon VARCHAR(16) NULL,
    is_private BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS knowledge_documents (
    id SERIAL PRIMARY KEY,
    space_id INTEGER NOT NULL REFERENCES knowledge_spaces(id) ON DELETE CASCADE,
    parent_id INTEGER NULL REFERENCES knowledge_documents(id) ON DELETE SET NULL,
    title VARCHAR(255) NOT NULL,
    slug VARCHAR(255) NOT NULL,
    summary TEXT NULL,
    content TEXT NOT NULL,
    is_published BOOLEAN NOT NULL DEFAULT FALSE,
    position INTEGER NOT NULL DEFAULT 0,
    version INTEGER NOT NULL DEFAULT 1,
    created_by_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    published_at TIMESTAMPTZ NULL,
    CONSTRAINT uq_knowledge_documents_space_slug UNIQUE (space_id, slug)
);

CREATE INDEX IF NOT EXISTS ix_kd_space_id ON knowledge_documents(space_id);
CREATE INDEX IF NOT EXISTS ix_kd_parent_id ON knowledge_documents(parent_id);
CREATE INDEX IF NOT EXISTS ix_kd_created_by_id ON knowledge_documents(created_by_id);

CREATE TABLE IF NOT EXISTS knowledge_document_revisions (
    id SERIAL PRIMARY KEY,
    document_id INTEGER NOT NULL REFERENCES knowledge_documents(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary TEXT NULL,
    content TEXT NOT NULL,
    created_by_id INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_knowledge_revision_document_version UNIQUE (document_id, version)
);

CREATE INDEX IF NOT EXISTS ix_kdr_document_id ON knowledge_document_revisions(document_id);
