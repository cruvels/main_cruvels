-- Migration: 001_initial_auth_and_memory.sql
-- Authoritative PostgreSQL Schema with Strict Ownership Constraints and Row-Level Security (RLS)

-- 1. Users Table
CREATE TABLE IF NOT EXISTS users (
    id VARCHAR(64) PRIMARY KEY,
    auth_provider VARCHAR(32) NOT NULL DEFAULT 'appwrite',
    auth_user_id VARCHAR(128) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    first_name VARCHAR(128),
    last_name VARCHAR(128),
    profile_image TEXT,
    account_status VARCHAR(32) NOT NULL DEFAULT 'active',
    password_hash VARCHAR(255),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_auth_user_id ON users(auth_user_id);
CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);

-- 2. User Settings Table
CREATE TABLE IF NOT EXISTS user_settings (
    user_id VARCHAR(64) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    auto_memory_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    preferred_style VARCHAR(64) DEFAULT 'Formal / Precise',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- 3. Conversations Table
CREATE TABLE IF NOT EXISTS conversations (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_user_id ON conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_created_at ON conversations(created_at DESC);

-- 4. Conversation Messages Table
CREATE TABLE IF NOT EXISTS conversation_messages (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    message_metadata TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conv_messages_conv_id ON conversation_messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conv_messages_user_id ON conversation_messages(user_id);
CREATE INDEX IF NOT EXISTS idx_conv_messages_created_at ON conversation_messages(created_at ASC);

-- 5. User Long-Term Memories Table
CREATE TABLE IF NOT EXISTS user_memories (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    memory_type VARCHAR(64) NOT NULL CHECK (memory_type IN ('PROFILE', 'PREFERENCE', 'WRITING_STYLE', 'WORKFLOW', 'CONTEXT')),
    memory_content TEXT NOT NULL,
    source_type VARCHAR(64) NOT NULL DEFAULT 'conversation',
    source_id VARCHAR(128),
    confidence REAL NOT NULL DEFAULT 1.0,
    importance REAL NOT NULL DEFAULT 0.5,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_user_memories_user_id ON user_memories(user_id);
CREATE INDEX IF NOT EXISTS idx_user_memories_type ON user_memories(user_id, memory_type);
CREATE INDEX IF NOT EXISTS idx_user_memories_status ON user_memories(status);

-- 6. Audit Logs Table
CREATE TABLE IF NOT EXISTS audit_logs (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL,
    operation VARCHAR(64) NOT NULL,
    resource_type VARCHAR(64) NOT NULL,
    resource_id VARCHAR(128),
    result VARCHAR(32) NOT NULL,
    details TEXT,
    timestamp TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_audit_logs_user_id ON audit_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_audit_logs_timestamp ON audit_logs(timestamp DESC);

-- 7. Ingested Documents
CREATE TABLE IF NOT EXISTS documents (
    document_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id VARCHAR(64) NOT NULL DEFAULT 'default_tenant',
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(32) NOT NULL,
    file_size INTEGER NOT NULL,
    checksum VARCHAR(128) NOT NULL,
    document_type VARCHAR(64) NOT NULL,
    classification_confidence REAL DEFAULT 0.0,
    case_id VARCHAR(64),
    access_scope VARCHAR(32) DEFAULT 'private',
    status VARCHAR(32) NOT NULL,
    original_file_location TEXT NOT NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_user_id ON documents(user_id);
CREATE INDEX IF NOT EXISTS idx_documents_case_id ON documents(user_id, case_id);

-- 8. Document Sections & Paragraphs
CREATE TABLE IF NOT EXISTS document_sections (
    section_id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    parent_section_id VARCHAR(64),
    title VARCHAR(255) NOT NULL,
    level INTEGER DEFAULT 1,
    page_number INTEGER DEFAULT 1,
    order_index INTEGER DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_doc_sections_doc ON document_sections(document_id);

CREATE TABLE IF NOT EXISTS document_paragraphs (
    paragraph_id VARCHAR(64) PRIMARY KEY,
    document_id VARCHAR(64) NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    section_id VARCHAR(64),
    page_number INTEGER DEFAULT 1,
    text TEXT NOT NULL,
    order_index INTEGER DEFAULT 0,
    is_clause INTEGER DEFAULT 0,
    clause_number VARCHAR(64)
);

CREATE INDEX IF NOT EXISTS idx_doc_paragraphs_doc ON document_paragraphs(document_id);

-- 9. Knowledge Units (Personal Knowledge Base)
CREATE TABLE IF NOT EXISTS knowledge_units (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id VARCHAR(64) NOT NULL DEFAULT 'default_tenant',
    document_id VARCHAR(64) NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    case_id VARCHAR(64),
    chunk_id VARCHAR(128) NOT NULL,
    parent_chunk_id VARCHAR(128),
    document_type VARCHAR(64),
    section_type VARCHAR(64),
    section_title VARCHAR(255),
    legal_topic VARCHAR(128),
    text TEXT NOT NULL,
    importance_score REAL DEFAULT 0.5,
    entities_json TEXT,
    concepts_json TEXT,
    claims_json TEXT,
    access_scope VARCHAR(32) DEFAULT 'private',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ku_user_id ON knowledge_units(user_id);
CREATE INDEX IF NOT EXISTS idx_ku_document_id ON knowledge_units(document_id);
CREATE INDEX IF NOT EXISTS idx_ku_case_id ON knowledge_units(user_id, case_id);

-- Row-Level Security Policies (Optional / Configurable via Application role)
-- To enable RLS in PostgreSQL:
-- ALTER TABLE conversations ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY user_conversations_isolation ON conversations FOR ALL USING (user_id = current_setting('app.current_user_id', true));
-- ALTER TABLE user_memories ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY user_memories_isolation ON user_memories FOR ALL USING (user_id = current_setting('app.current_user_id', true));
-- ALTER TABLE documents ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY user_documents_isolation ON documents FOR ALL USING (user_id = current_setting('app.current_user_id', true));
