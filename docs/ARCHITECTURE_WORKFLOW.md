# Cruvels AI Legal Knowledge Platform — Layer-by-Layer Architectural Specification

Comprehensive, end-to-end technical blueprint for the **Cruvels AI Legal Knowledge Platform**, documenting all 8 operational layers, data flows, database schemas, sequence diagrams, and security guardrails.

---

## Table of Contents
1. [Executive Overview & Architectural Philosophy](#1-executive-overview--architectural-philosophy)
2. [Global Architecture Blueprint (Top-Level Topology)](#2-global-architecture-blueprint-top-level-topology)
3. [Layer-by-Layer Detailed Workflow](#3-layer-by-layer-detailed-workflow)
   - [Layer 1: Identity, Authentication & Zero-Trust Security](#layer-1-identity-authentication--zero-trust-security)
   - [Layer 2: Document Ingestion, Structural Decomposition & Knowledge Extraction](#layer-2-document-ingestion-structural-decomposition--knowledge-extraction)
   - [Layer 3: Personal AI Memory Studio](#layer-3-personal-ai-memory-studio)
   - [Layer 4: Hybrid Knowledge Retrieval & Permission Scoping](#layer-4-hybrid-knowledge-retrieval--permission-scoping)
   - [Layer 5: Multi-Agent Orchestration & Reasoning Core (LangGraph)](#layer-5-multi-agent-orchestration--reasoning-core-langgraph)
   - [Layer 6: Legal Drafting Engine & Empirical Style Transformation](#layer-6-legal-drafting-engine--empirical-style-transformation)
   - [Layer 7: Storage & Persistence Subsystem (Database Architecture)](#layer-7-storage--persistence-subsystem-database-architecture)
   - [Layer 8: Client Application & Web Presentation Layer](#layer-8-client-application--web-presentation-layer)
4. [End-to-End Workflow Sequence Diagrams](#4-end-to-end-workflow-sequence-diagrams)
   - [Workflow 1: Document Ingestion & Knowledge Indexing Flow](#workflow-1-document-ingestion--knowledge-indexing-flow)
   - [Workflow 2: Grounded Legal Q&A Query Execution Flow](#workflow-2-grounded-legal-qa-query-execution-flow)
   - [Workflow 3: Personal AI Memory Extraction & Recall Lifecycle](#workflow-3-personal-ai-memory-extraction--recall-lifecycle)
   - [Workflow 4: Style Extraction & Legal Document Drafting Flow](#workflow-4-style-extraction--legal-document-drafting-flow)
5. [Security, Zero-Hallucination & Isolation Matrix](#5-security-zero-hallucination--isolation-matrix)
6. [Deployment & Environmental Configuration](#6-deployment--environmental-configuration)

---

## 1. Executive Overview & Architectural Philosophy

The **Cruvels AI Legal Knowledge Platform** is an enterprise-grade AI system built specifically for legal professionals. Unlike general-purpose conversational LLMs, Cruvels AI enforces deterministic legal guarantees:

- **Zero-Hallucination Mandate:** The model is prohibited from synthesizing legal assertions without citing an exact, verifiable source clause (`filename`, `section`, and `page_number`). If evidence is insufficient, it triggers a strict fallback refusal.
- **Strict Multi-Tenant & User Isolation:** Complete separation of user data across SQLite, PostgreSQL, ChromaDB, and disk storage. Client-supplied IDs are never trusted. Identity is verified via server-side session tokens.
- **Dynamic Personal AI Memory:** Automatically remembers lawyer preferences, jurisdiction constraints, drafting rules, and case facts over time, injecting user-specific context into future interactions without cross-user leakage.
- **Empirical Style Synthesis:** Analyzes an attorney's historical filings to extract real structural metrics (sentence length, clause patterns, formality index) and applies them during grounded legal drafting.

---

## 2. Global Architecture Blueprint (Top-Level Topology)

```mermaid
flowchart TB
    subgraph L8 ["Layer 8: Client Presentation Layer (SPA)"]
        UI_QA["Legal Q&A / RAG Studio"]
        UI_Draft["Legal Drafting & Style Studio"]
        UI_Insp["Knowledge Inspector"]
        UI_Mem["Personal AI Memory Studio"]
    end

    subgraph L1 ["Layer 1: Identity & Zero-Trust Security Gateway"]
        AuthSvc["Appwrite Cloud / HMAC-SHA256 Token Service"]
        FastAPI_Auth["FastAPI Depends(get_current_user)"]
        AuthScope["AuthorizedScope (user_id, case_id, access_scope)"]
    end

    subgraph L2 ["Layer 2: Ingestion & Knowledge Extraction Pipeline"]
        DocLoader["Multi-Format Loader (PDF/TXT/DOCX)"]
        Parser["PyMuPDF Native Parser + PaddleOCR-VL Fallback"]
        SemParser["Semantic Legal Parser (Sections/Clauses)"]
        KUExtract["Knowledge Unit Extractor & Scorer (0.0 - 1.0)"]
    end

    subgraph L3 ["Layer 3: Personal AI Memory Studio"]
        MemClassifier["Memory Classifier (PREFERENCE, STYLE, CONTEXT)"]
        MemRepo["UserMemoryRepository"]
        MemSync["Chroma User-Memory Vector Namespace"]
    end

    subgraph L4 ["Layer 4: Hybrid Knowledge Retrieval Engine"]
        QAnalyzer["Legal Query Analyzer"]
        HybridSearch["3-Way Hybrid Search (Semantic 0.6 + BM25 0.2 + Score 0.2)"]
        ScopeFilter["Strict User & Case Isolation Filter"]
    end

    subgraph L5 ["Layer 5: Multi-Agent Reasoning Core (LangGraph)"]
        AgentState["LangGraph State Machine (AgentState)"]
        AgentNode["Reasoning Node (Kimi K2.5 / OpenRouter)"]
        ToolNode["Tool Execution Node (document_search)"]
        VerifierNode["Grounded Citation & Hallucination Guardrail"]
    end

    subgraph L6 ["Layer 6: Legal Drafting & Style Engine"]
        StyleEngine["Empirical Style Profiler (Avg Len, Formality, Tone)"]
        DraftingAgent["Drafting Agent (Content + Style Synthesis)"]
        DraftFallback["Deterministic Rule-Based Legal Fallback"]
        ClaimValidator["Citation & Statutory Claim Validator"]
    end

    subgraph L7 ["Layer 7: Multi-Tier Storage & Persistence"]
        DB_Relational["PostgreSQL / SQLite (Users, Mem, Docs, Conv, KU)"]
        DB_Vector["ChromaDB Vector Store (HNSW Graph + Embeddings)"]
        FS_Storage["Encrypted File System (User-Scoped Uploads)"]
    end

    %% Interactions
    L8 <-->|Bearer Token HTTP/JSON| L1
    L1 --> AuthScope
    AuthScope --> L4
    AuthScope --> L3
    AuthScope --> L2

    L2 --> DB_Relational
    L2 --> DB_Vector
    L2 --> FS_Storage

    L3 <--> DB_Relational
    L3 <--> DB_Vector
    L3 -.->|Injected Memory Context| L5

    L4 <--> DB_Vector
    L4 <--> DB_Relational
    L4 -->|Context Packages| L5
    L4 -->|Context Packages| L6

    L5 <--> L4
    L5 --> DB_Relational

    L6 <--> StyleEngine
    L6 --> ClaimValidator
    L6 --> DraftFallback
    L6 --> DB_Relational
```

---

## 3. Layer-by-Layer Detailed Workflow

### Layer 1: Identity, Authentication & Zero-Trust Security

The security layer guarantees that **no client request is ever trusted without cryptographic verification**.

```
Client HTTP Request
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Header: Authorization: Bearer <session_token>           │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ FastAPI Dependency: get_current_user()                 │
│ 1. Validate against Appwrite Cloud REST endpoint       │
│ 2. If Appwrite is paused/unreachable:                  │
│    Validate against local HMAC-SHA256 Token Store      │
│    (PBKDF2-SHA256 salt+hash)                           │
│ 3. Resolve UserModel(id, email, account_status)        │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Construct AuthorizedScope Context:                     │
│ - user_id = current_user.id                            │
│ - case_id = request.case_id                            │
│ - allowed_visibilities = ('private', 'shared', 'firm') │
└────────────────────────────────────────────────────────┘
```

#### Key Components:
- **`src/auth/appwrite_service.py`**: Interacts with Appwrite Cloud (`users.create`, `account.create_email_password_session`). Includes resilient local fallback when cloud project is paused or offline.
- **`src/auth/dependencies.py`**: `get_current_user()` and `get_optional_user()` extract the session token, verify identity, and bind the user to `request.state.user`.
- **`src/context/scope.py`**: Creates an immutable `AuthorizedScope` object containing permission boundaries passed downstream into every retrieval and database call.

---

### Layer 2: Document Ingestion, Structural Decomposition & Knowledge Extraction

Transforms raw, unstructured legal files (PDF, TXT, DOCX) into clean, structured, and searchable **Knowledge Units**.

```
Upload File (POST /api/upload)
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Dual-Engine Ingestion (src/ingestion/loader.py):       │
│ - Primary: PyMuPDF high-speed native digital text      │
│ - Fallback: PaddleOCR-VL for scanned/low-density pages │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Semantic Legal Parser (src/ingestion/parsers.py):      │
│ - Detect Titles, Articles, Sections, Clauses           │
│ - Extract numbered clauses (e.g., '2.1', 'Section 4')  │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Contextual Chunking & Importance Scoring:              │
│ - RecursiveCharacterTextSplitter (800 chars / 120 ovl) │
│ - Calculate Importance Score (0.0 to 1.0)              │
│ - Extract Entities, Concepts, and Statutory Claims     │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Vector Embedding Generation:                           │
│ - Model: BAAI/bge-small-en-v1.5 (384-dimensional)      │
│ - Batched generation via In-Memory Singleton           │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Dual Persistent Storage:                               │
│ 1. ChromaDB: Dense vector + chunk metadata             │
│ 2. Relational DB: documents, sections, knowledge_units │
└────────────────────────────────────────────────────────┘
```

#### Key Components:
- **`src/ingestion/loader.py`**: Handles PDF, DOCX, TXT. Detects image-based PDFs automatically and routes them to OCR.
- **`src/ingestion/parsers.py`**: Regex and structural rule parser that identifies legal headings, definitions, and recitals.
- **`src/context/pkb.py`**: Structures document excerpts into `KnowledgeUnit` objects containing `importance_score`, `entities`, and `claims`.
- **`src/retrieval/embeddings.py`**: Manages `BAAI/bge-small-en-v1.5` dense embedding generation with local caching.

---

### Layer 3: Personal AI Memory Studio

The Memory Studio enables Cruvels AI to maintain **long-term cognitive memory** across conversations while preventing cross-user data leakage.

```
Incoming Turn / Message
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Memory Extraction Agent (src/memory/service.py):       │
│ Evaluates whether message contains stable facts:       │
│ - User preferences (e.g., "Draft in UK English")       │
│ - Drafting tone (e.g., "Always use formal tone")       │
│ - Specific case context & party relationships          │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Classification & Taxonomy:                             │
│ - PROFILE: User role, bar jurisdiction, firm name      │
│ - PREFERENCE: Explicit instruction for future replies  │
│ - WRITING_STYLE: Sentence structure, phrase avoidance  │
│ - WORKFLOW: Preferred review steps, checklist needs    │
│ - CONTEXT: Client or matter background                 │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Deduplication & Persistence:                           │
│ - Calculates similarity against existing user memories │
│ - Saves to user_memories table (PostgreSQL/SQLite)     │
│ - Indexes memory embedding into Chroma user collection │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Dynamic Prompt Injection (src/api/main.py):            │
│ Retrieved memories for current user are injected into  │
│ LLM System Prompt under [USER PREFERENCES & MEMORY]   │
└────────────────────────────────────────────────────────┘
```

#### Memory Attributes:
| Field | Type | Description |
|---|---|---|
| `id` | `VARCHAR(64)` | Unique memory identifier (`mem_<uuid>`) |
| `user_id` | `VARCHAR(64)` | Strictly isolated owner identifier |
| `memory_type` | `ENUM` | `PROFILE`, `PREFERENCE`, `WRITING_STYLE`, `WORKFLOW`, `CONTEXT` |
| `memory_content`| `TEXT` | Concise natural language fact |
| `importance` | `REAL` | Importance weighting (0.1 to 1.0) |
| `confidence` | `REAL` | Extraction confidence (0.0 to 1.0) |
| `status` | `VARCHAR(32)`| `active`, `archived`, `deleted` |

---

### Layer 4: Hybrid Knowledge Retrieval & Permission Scoping

Combines semantic similarity, lexical keyword matching, and document importance into a unified, permission-scoped retrieval score.

```
Incoming Legal Query
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Query Analysis (src/retrieval/hybrid.py):              │
│ - Identifies key legal concepts & statutory sections   │
│ - Determines intent (Definition, Obligation, Defense)  │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ 3-Way Scoring Computation:                             │
│                                                        │
│ Score = (0.60 * S_semantic)                            │
│       + (0.20 * S_keyword)                             │
│       + (0.20 * S_importance)                          │
│                                                        │
│ - S_semantic: Cosine similarity via BAAI/bge-small     │
│ - S_keyword: BM25 / token overlap score                │
│ - S_importance: Structural legal weight (0.0 - 1.0)    │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Permission & Threshold Filter:                         │
│ - WHERE user_id == scope.user_id                       │
│ - AND (case_id == scope.case_id OR case_id IS NULL)    │
│ - AND score >= 0.20                                    │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Top-K Context Packages (k=5):                          │
│ Emits ContextPackage with exact filename & page bounds │
└────────────────────────────────────────────────────────┘
```

#### Scoring Weights Rationale:
- **Semantic Score (60%):** Captures conceptual alignment across phrasing variations (e.g., *"limitation of liability"* matching *"cap on damages"*).
- **Keyword Score (20%):** Guarantees exact statutory references (e.g., *"Section 73"*, *"Clause 14.2"*) are never missed.
- **Importance Score (20%):** Prioritizes primary clauses and definitions over incidental footnotes or recitals.

---

### Layer 5: Multi-Agent Orchestration & Reasoning Core (LangGraph)

The cognitive center coordinates legal reasoning, searches the knowledge base via bounded tool executions, and verifies evidence.

```mermaid
stateDiagram-v2
    [*] --> InitializeState
    InitializeState --> AgentReasoning: Bind Tools & Scope
    
    state AgentReasoning {
        [*] --> LLM_Inference
        LLM_Inference --> InspectToolCalls
    }

    AgentReasoning --> ToolExecutionNode: Has Tool Calls
    AgentReasoning --> FinalizeNode: No Tool Calls (Finished)

    state ToolExecutionNode {
        [*] --> ExecuteSearch
        ExecuteSearch --> DocumentSearch: query, scope
        ExecuteSearch --> MetadataLookup: doc_id
        DocumentSearch --> AggregateResults
        MetadataLookup --> AggregateResults
    }

    ToolExecutionNode --> AgentReasoning: Append Tool Output to State

    state FinalizeNode {
        [*] --> VerifyGrounding
        VerifyGrounding --> ValidSourcesFound: Evidence Exists
        VerifyGrounding --> InsufficientEvidence: No Valid Chunks
        ValidSourcesFound --> FormatWithCitations: Attach Source Chips
        InsufficientEvidence --> DeterministicFallback: "I don't have enough info..."
    }

    FormatWithCitations --> [*]
    DeterministicFallback --> [*]
```

#### Agent State Structure (`AgentState`):
- `messages`: List of LangChain messages (`SystemMessage`, `HumanMessage`, `AIMessage`, `ToolMessage`).
- `authorized_scope`: Attached user boundary (`user_id`, `case_id`).
- `retrieved_chunks`: Accumulated candidate chunks verified by tool calls.
- `iteration_count`: Circuit breaker limit (maximum 4 tool execution steps).

---

### Layer 6: Legal Drafting Engine & Empirical Style Transformation

Transforms legal instructions into formal notices, contracts, and court filings while applying the attorney's personalized style profile.

```
Drafting Request (POST /api/drafting/generate)
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Style Profiler (src/agent/drafting.py):                │
│ - Analyzes uploaded user documents                     │
│ - Measures: Average Sentence Length (words)            │
│ - Measures: Formality Index (0.0 - 1.0)                │
│ - Extracts: Preferred Terms ("whereas", "forthwith")   │
│ - Extracts: Avoided Terms ("maybe", "kinda")           │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Contextual Knowledge Retrieval:                        │
│ - Hybrid Search retrieves relevant clauses & evidence  │
│ - Structures evidence into provenance records          │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Two-Stage Synthesis Prompting:                         │
│ 1. Content Grounding: Strict adherence to facts/dates  │
│ 2. Style Transformation: Enforce tone, sentence length │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ LLM Generation with Fail-Safe Fallback:                │
│ - Primary: OpenRouter Kimi K2.5 (1200 max_tokens)      │
│ - Resilient Fallback: Rule-Based Grounded Generator    │
│   (Guarantees full legal draft even on API quota caps) │
└────────────────────────────────────────────────────────┘
       │
       ▼
┌────────────────────────────────────────────────────────┐
│ Deterministic Citation & Claim Validation:             │
│ - Validates references to statutory sections           │
│ - Emits validation_notes with verified citations       │
└────────────────────────────────────────────────────────┘
```

---

### Layer 7: Storage & Persistence Subsystem (Database Architecture)

Cruvels AI utilizes a hybrid storage architecture:

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Storage Subsystem Architecture                  │
├──────────────────────────┬───────────────────────┬───────────────────────┤
│ Relational Database      │ Vector Database       │ File System Storage   │
│ (PostgreSQL / SQLite)    │ (ChromaDB + HNSW)     │ (Encrypted OS Disk)   │
├──────────────────────────┼───────────────────────┼───────────────────────┤
│ • users                  │ • data/vectorstore/   │ • data/uploads/       │
│ • user_settings          │   chroma.sqlite3      │   {user_id}/          │
│ • conversations          │ • HNSW Index Graph    │   original_files/     │
│ • conversation_messages  │   (data_level0.bin)   │                       │
│ • user_memories          │ • Collections:        │                       │
│ • documents              │   - legal_documents   │                       │
│ • document_sections      │   - user_memories     │                       │
│ • document_paragraphs    │                       │                       │
│ • knowledge_units        │                       │                       │
│ • style_profiles         │                       │                       │
│ • templates              │                       │                       │
│ • audit_logs             │                       │                       │
└──────────────────────────┴───────────────────────┴───────────────────────┘
```

#### Full Database Table Schema Summary:

```sql
-- 1. Users
CREATE TABLE users (
    id VARCHAR(64) PRIMARY KEY,
    auth_provider VARCHAR(32) NOT NULL DEFAULT 'appwrite',
    auth_user_id VARCHAR(128) NOT NULL UNIQUE,
    email VARCHAR(255) NOT NULL UNIQUE,
    first_name VARCHAR(128),
    last_name VARCHAR(128),
    account_status VARCHAR(32) NOT NULL DEFAULT 'active',
    password_hash VARCHAR(255),
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 2. User Settings
CREATE TABLE user_settings (
    user_id VARCHAR(64) PRIMARY KEY REFERENCES users(id) ON DELETE CASCADE,
    auto_memory_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    preferred_style VARCHAR(64) DEFAULT 'Formal / Precise',
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 3. Conversations
CREATE TABLE conversations (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 4. Conversation Messages
CREATE TABLE conversation_messages (
    id VARCHAR(64) PRIMARY KEY,
    conversation_id VARCHAR(64) NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(32) NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content TEXT NOT NULL,
    message_metadata TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 5. User Memories
CREATE TABLE user_memories (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    memory_type VARCHAR(64) NOT NULL,
    memory_content TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 1.0,
    importance REAL NOT NULL DEFAULT 0.5,
    status VARCHAR(32) NOT NULL DEFAULT 'active',
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 6. Ingested Documents
CREATE TABLE documents (
    document_id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    tenant_id VARCHAR(64) NOT NULL DEFAULT 'default_tenant',
    filename VARCHAR(255) NOT NULL,
    file_type VARCHAR(32) NOT NULL,
    file_size INTEGER NOT NULL,
    checksum VARCHAR(128) NOT NULL,
    case_id VARCHAR(64),
    status VARCHAR(32) NOT NULL,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- 7. Knowledge Units (Personal Knowledge Base)
CREATE TABLE knowledge_units (
    id VARCHAR(64) PRIMARY KEY,
    user_id VARCHAR(64) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    document_id VARCHAR(64) NOT NULL REFERENCES documents(document_id) ON DELETE CASCADE,
    chunk_id VARCHAR(128) NOT NULL,
    section_title VARCHAR(255),
    legal_topic VARCHAR(128),
    text TEXT NOT NULL,
    importance_score REAL DEFAULT 0.5,
    entities_json TEXT,
    concepts_json TEXT,
    claims_json TEXT,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);
```

---

### Layer 8: Client Application & Web Presentation Layer

The front end is an interactive Single-Page Application (SPA) designed with a modern dark theme and strict responsive layout.

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          Cruvels AI Web Studio                           │
├─────────────┬────────────────────────────────────────────────────────────┤
│ SIDEBAR     │ MAIN WORKSPACE VIEWPORT                                    │
│             ├────────────────────────────────────────────────────────────┤
│ • Status:   │ TABS: [Legal Q&A] [Drafting & Style] [Inspector] [Memory]  │
│   API Ready ├────────────────────────────────────────────────────────────┤
│ • Active LLM│ TAB 1: Real-Time Chat & Grounded Sources Viewport          │
│ • History:  │ - Chat thread with markdown parsing via marked.js          │
│   1-Click   │ - Verifiable source pills with modal preview               │
│   Load / Del├────────────────────────────────────────────────────────────┤
│ • Documents:│ TAB 2: Drafting & Style Studio                             │
│   Upload    │ - Document Type dropdown & Instructions editor             │
│   Listing   │ - Empirical style badge & "Re-analyze My Style" button     │
│   Deletions │ - Full draft preview with validation notes & 1-click copy  │
│ • Profile:  ├────────────────────────────────────────────────────────────┤
│   Active User│ TAB 3: Structured Knowledge Inspector                      │
│   Logout    │ - Document section hierarchy & entity extraction tags      │
│             ├────────────────────────────────────────────────────────────┤
│             │ TAB 4: Personal AI Memory Studio                           │
│             │ - Categorized memory cards with importance scores          │
│             │ - Create manual memory modal & toggle auto-learning        │
└─────────────┴────────────────────────────────────────────────────────────┘
```

---

## 4. End-to-End Workflow Sequence Diagrams

### Workflow 1: Document Ingestion & Knowledge Indexing Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as Attorney (User)
    participant UI as Web Frontend (app.js)
    participant API as FastAPI Gateway (/api/upload)
    participant Auth as Auth Dependency (get_current_user)
    participant Ingest as Loader & Semantic Parser
    participant Embed as BGE Embedding Engine
    participant Chroma as ChromaDB Vector Store
    participant DB as Relational Database

    User->>UI: Upload Legal Document (PDF / DOCX)
    UI->>API: POST /api/upload (multipart/form-data + Bearer token)
    API->>Auth: Verify Session Token
    Auth-->>API: Valid UserModel(user_id)
    API->>Ingest: Process file stream
    Ingest->>Ingest: PyMuPDF text extraction (or PaddleOCR fallback)
    Ingest->>Ingest: Semantic section & numbered clause extraction
    Ingest->>Ingest: Contextual Chunking & KnowledgeUnit scoring
    Ingest->>Embed: Compute 384-dim embeddings for all chunks
    Embed-->>Ingest: Dense vector embeddings array
    Ingest->>Chroma: Index vectors with metadata (user_id, doc_id, page_no)
    Ingest->>DB: INSERT INTO documents, sections, knowledge_units
    API-->>UI: HTTP 200 OK (document_id, chunk_count, status)
    UI->>User: Display document pill & updated Knowledge Base listing
```

---

### Workflow 2: Grounded Legal Q&A Query Execution Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as Attorney (User)
    participant UI as Web Frontend (app.js)
    participant API as FastAPI Gateway (/api/ask)
    participant Mem as Memory Service
    participant LG as LangGraph Agent Core
    participant Tools as Tool Execution Node
    participant Chroma as ChromaDB
    participant LLM as OpenRouter (Kimi K2.5)
    participant DB as Relational Database

    User->>UI: Submit Legal Query ("What is the confidentiality term?")
    UI->>API: POST /api/ask { question, conversation_id }
    API->>API: Enforce user_id from verified token
    API->>Mem: retrieve_relevant_memories(user_id, question)
    Mem-->>API: Active user preferences & drafting rules
    API->>DB: Save user message in conversation_messages
    API->>LG: Execute AgentState graph with scope & memories
    LG->>LLM: Synthesize query & decide tool calls
    LLM-->>LG: Call document_search(query)
    LG->>Tools: Execute document_search with AuthorizedScope
    Tools->>Chroma: Query ANN similarity (user_id filter applied)
    Chroma-->>Tools: Top-K Grounded Chunks (threshold >= 0.20)
    Tools-->>LG: Return chunks as ToolMessage
    LG->>LLM: Generate final answer with mandatory citations
    LLM-->>LG: Final cited answer text
    LG->>LG: Verify Grounding (ensure citations exist)
    LG-->>API: Grounded Answer + Source Metadata list
    API->>DB: Save assistant response in conversation_messages
    API-->>UI: HTTP 200 OK { answer, sources, conversation_id }
    UI->>User: Render markdown response + Clickable source citations
```

---

### Workflow 3: Personal AI Memory Extraction & Recall Lifecycle

```mermaid
sequenceDiagram
    autonumber
    actor User as Attorney (User)
    participant UI as Web Frontend
    participant API as FastAPI /api/ask
    participant MemSvc as Memory Service (extract_from_conversation)
    participant LLM as Memory Analyzer LLM
    participant DB as Relational DB (user_memories)
    participant Chroma as ChromaDB (user_memories)

    User->>UI: "I represent Tenant in Delhi jurisdiction. Use formal style."
    UI->>API: Send message turn
    API->>API: Complete standard Q&A flow
    API->)MemSvc: Trigger background memory extraction
    MemSvc->>LLM: Analyze turn for stable facts/rules
    LLM-->>MemSvc: Extracted: [Jurisdiction: Delhi], [Style: Formal]
    MemSvc->>DB: Check for duplicate memory
    alt Not Duplicate
        MemSvc->>DB: INSERT INTO user_memories (type='CONTEXT', 'STYLE')
        MemSvc->>Chroma: Index memory embedding
    end
    Note over User, UI: In Next Session
    User->>UI: Submit new drafting query
    UI->>API: POST /api/ask
    API->>MemSvc: retrieve_relevant_memories(user_id)
    MemSvc-->>API: Returns: "Jurisdiction: Delhi", "Style: Formal"
    API->>API: Injects memories directly into LLM system prompt
```

---

### Workflow 4: Style Extraction & Legal Document Drafting Flow

```mermaid
sequenceDiagram
    autonumber
    actor User as Attorney (User)
    actor UI as Web Frontend (Drafting Tab)
    participant API as FastAPI (/api/drafting/generate)
    participant Style as StyleEngine
    participant Hybrid as Hybrid Retriever
    participant Agent as DraftingAgent
    participant LLM as OpenRouter LLM (1200 tokens)
    participant DB as Relational Database

    User->>UI: Select "Arbitration Notice" & Enter Instructions
    UI->>API: POST /api/drafting/generate { document_type, instructions }
    API->>API: Set req.user_id = current_user.id
    API->>Style: get_style_profile(user_id)
    Style-->>API: StyleProfile (avg_len: 22.5, tone: 'formal', format: 'numbered')
    API->>Hybrid: retrieve(query=instructions, user_id=user_id)
    Hybrid-->>API: Context packages (relevant agreement clauses)
    API->>Agent: generate_draft(req, evidence, style)
    Agent->>LLM: Invoke 2-Stage System Prompt (Content + Style constraints)
    alt LLM Generates Successfully
        LLM-->>Agent: Full drafted document
    else LLM Exhaustion / Timeout
        Agent->>Agent: Run _generate_grounded_fallback()
        Note over Agent: Synthesizes fully structured legal draft with clauses & evidence
    end
    Agent->>Agent: _validate_draft() for statutory citations
    Agent-->>API: DraftingResponse { title, content, validation_notes }
    API-->>UI: HTTP 200 OK
    UI->>User: Display rendered draft preview + validation checklist
```

---

## 5. Security, Zero-Hallucination & Isolation Matrix

| Threat Vector | Mitigation Architecture | Verification Mechanism |
|---|---|---|
| **Cross-User Data Leakage** | All database queries use parameter binding with `current_user.id`. Chroma queries apply metadata filter `{"user_id": scope.user_id}`. | `tests/test_auth_memory_isolation.py` (User A cannot read User B's memories or documents). |
| **Tampered Resource IDs** | Endpoints reject requests if `resource.user_id != current_user.id` (returns HTTP 404/403). | Automatic test assertions for manipulated conversation IDs and memory IDs. |
| **LLM Hallucination** | System prompt instructs agent to cite page and clause bounds. Finalize node verifies evidence presence. If missing, emits strict fallback text. | Grounded Citation Verification test suite (`test_grounded_fallback`). |
| **Token Budget Starvation** | OpenRouter `max_tokens` calibrated to `1200` to prevent HTTP 402 errors. Drafting engine includes automatic rule-based grounded fallback. | End-to-end drafting test verification under constrained token limits. |
| **Authentication Outages** | Dual authentication engine: transparently switches from Appwrite Cloud to local HMAC-SHA256 PBKDF2 tokens if cloud API is paused. | Live health check endpoint verifies fallback availability. |

---

## 6. Deployment & Environmental Configuration

### Core Environment Variables (`.env`)
```bash
# Model & Provider Configuration
LLM_PROVIDER=openrouter
LLM_MODEL=moonshotai/kimi-k2.5
OPENROUTER_API_KEY=your_openrouter_api_key

# Authentication (Appwrite + Local Fallback)
APPWRITE_ENDPOINT=https://cloud.appwrite.io/v1
APPWRITE_PROJECT_ID=your_project_id
APPWRITE_API_KEY=your_secret_api_key
SECRET_KEY=your_hmac_sha256_token_signing_secret

# Database Configuration
DATABASE_URL=sqlite:///./data/processed/legal_kb.sqlite3
# For PostgreSQL: postgresql://postgres:password@localhost:5432/cruvels_legal_db

# Retrieval & Vector Database
VECTORSTORE_DIR=./data/vectorstore
EMBEDDING_MODEL=BAAI/bge-small-en-v1.5
```

### Production Launch Command (Windows & Linux Compatible)
```bash
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 7860 --workers 1
```

---
*Cruvels AI — Enterprise Legal Intelligence Platform*  
*Document Version: 1.0 (Comprehensive Architecture Blueprint)*
