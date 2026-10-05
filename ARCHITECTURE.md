# Cruvels AI Legal Knowledge Assistant — System Architecture

Comprehensive architectural specification for the **Cruvels AI Legal Knowledge Assistant**, including end-to-end data flow, multi-agent orchestration, OCR ingestion pipeline, and dedicated vector database subsystem.

---

## 1. End-to-End System Architecture

```mermaid
flowchart TB
    subgraph Client ["Client Presentation Layer"]
        UI["Web Interface (HTML5 / Vanilla CSS / Modern JS)"]
        ChatModule["Chat & Real-time Markdown Renderer"]
        DocList["Ingested Document Viewer"]
        DynamicPrompt["Dynamic Document Suggestion Pills"]
    end

    subgraph API_Gateway ["API & Web Server (FastAPI + Uvicorn)"]
        Router["FastAPI Application Router"]
        StaticServer["Static Files Mount (/)"]
        AuthMiddleware["CORS & Request Validation (Pydantic v2)"]
        
        EP_Upload["POST /api/upload"]
        EP_Ask["POST /api/ask"]
        EP_Docs["GET /api/documents"]
        EP_Sugg["GET /api/suggestions"]
        EP_Clear["DELETE /api/knowledge-base"]
        EP_Health["GET /api/health"]
    end

    subgraph Ingestion_Pipeline ["Document Processing Pipeline"]
        Loader["Document Loader (src/ingestion/loader.py)"]
        PyMuPDF["PyMuPDF Native Text Parser"]
        OCR_Engine["PaddleOCR-VL Scanned Page OCR"]
        Chunker["RecursiveCharacterTextSplitter (800 chars / 120 overlap)"]
    end

    subgraph Vector_DB ["Vector Database & Retrieval Subsystem (ChromaDB)"]
        EmbeddingEngine["Embeddings Engine (BAAI/bge-small-en-v1.5)"]
        ChromaStore["Chroma Vector Store (data/vectorstore)"]
        HNSW_Index["HNSW Index (Cosine Similarity)"]
        SQLite_Metadata["SQLite Document & Chunk Metadata Store"]
        SelfHealing["Self-Healing Recovery Wrapper"]
    end

    subgraph Agent_Core ["Agentic Reasoning Core (LangGraph)"]
        StateGraph["LangGraph State Machine (AgentState)"]
        AgentNode["LLM Agent Node (Tool Binding)"]
        ToolNode["Tool Execution Node"]
        SearchTool["document_search Tool"]
        MetaTool["document_metadata_lookup Tool"]
        FinalizeNode["Finalize & Grounded Citation Verification"]
    end

    subgraph Security_Layer ["Access Control & Permissions (src/context)"]
        Scope["AuthorizedScope (Role, User ID, Case ID, Visibility)"]
    end

    subgraph External_LLM ["External Model Providers"]
        OpenRouter["OpenRouter Gateway"]
        Model_Kimi["Moonshot Kimi K2.5 / Claude Sonnet"]
    end

    %% Connections
    UI --> Router
    ChatModule --> EP_Ask
    DocList --> EP_Docs
    DynamicPrompt --> EP_Sugg
    
    EP_Upload --> Loader
    Loader -->|Native Digital PDF| PyMuPDF --> Chunker
    Loader -->|Scanned / Image Page| OCR_Engine --> Chunker
    Chunker --> EmbeddingEngine --> SelfHealing --> ChromaStore
    ChromaStore --> HNSW_Index
    ChromaStore --> SQLite_Metadata

    EP_Ask --> Scope --> StateGraph
    StateGraph --> AgentNode
    AgentNode <--> OpenRouter <--> Model_Kimi
    AgentNode -->|Tool Calls| ToolNode
    ToolNode --> SearchTool --> HNSW_Index
    ToolNode --> MetaTool --> SQLite_Metadata
    ToolNode --> AgentNode
    AgentNode --> FinalizeNode
    FinalizeNode -->|Grounded Response + Sources| EP_Ask
```

---

## 2. Dedicated Vector Database & Retrieval Architecture

```mermaid
flowchart LR
    subgraph INGESTION ["1. Ingestion & Embedding Flow"]
        direction TB
        RawFile["Document Upload<br/>(PDF / TXT / DOCX)"]
        CleanDoc["Cleaned Page Text & Metadata<br/>(file_name, page_number, doc_id)"]
        Chunks["Chunked Fragments<br/>(size: 800, overlap: 120)"]
        EmbedGen["Dense Embeddings (384-dim)<br/>BAAI/bge-small-en-v1.5"]

        RawFile --> CleanDoc --> Chunks --> EmbedGen
    end

    subgraph CHROMADB ["2. ChromaDB Storage Engine"]
        direction TB
        subgraph Storage ["Persistent Storage (data/vectorstore/)"]
            HNSW["HNSW Graph Index<br/>(data_level0.bin, link_lists.bin)"]
            SQLite["SQLite Metadata DB<br/>(chroma.sqlite3: collections, chunks, tenants)"]
        end
        
        subgraph Logic ["Resilient Access Layer"]
            Singleton["_CACHED_VECTORSTORE Singleton"]
            AddTexts["add_texts() Non-Destructive Ingestion"]
            AutoHeal["Auto Schema Recovery Handler"]
        end
        
        Logic <--> Storage
    end

    subgraph RETRIEVAL ["3. Retrieval & Scoping Flow"]
        direction TB
        UserQ["User Query"]
        QEmbed["Query Vector (384-dim)"]
        KCandidates["Top-K ANN Search (k=10)"]
        ScoreFilter["Score Filter (threshold >= 0.20)"]
        AuthFilter["AuthorizedScope Filter<br/>(visibility / case_id)"]
        FinalSources["Grounded Chunks (Top 5)<br/>with Page & File Citations"]

        UserQ --> QEmbed --> KCandidates --> ScoreFilter --> AuthFilter --> FinalSources
    end

    EmbedGen --> AddTexts
    Storage <--> KCandidates
```

---

## 3. Data Flow & Lifecycle Specification

### A. Document Ingestion Lifecycle
1. **Upload**: Client sends `multipart/form-data` to `/api/upload`.
2. **Parsing**: PyMuPDF extracts native text per page. If text density is below threshold, PaddleOCR-VL runs per-page OCR.
3. **Chunking**: `RecursiveCharacterTextSplitter` divides text into overlapping segments (800 chars / 120 overlap).
4. **Vector Generation**: `BAAI/bge-small-en-v1.5` creates 384-dimensional dense vectors in batched operations.
5. **Storage**: Vectors and metadata (`doc_id`, `file_name`, `page_number`, `visibility`) are indexed into ChromaDB.

### B. Agentic Q&A Query Lifecycle
1. **Query Ingestion**: Client submits prompt to `/api/ask`.
2. **Context Creation**: `AuthorizedScope` is attached to bind security boundaries.
3. **Agent Loop (LangGraph)**:
   - System prompt configures the agent to act as a rigorous legal assistant.
   - LLM decides whether to call `document_search(query)` or `document_metadata_lookup(doc_id)`.
   - Tool calls execute bounded searches (max budget: 4 iterations).
4. **Grounded Citation Verification**:
   - `finalize` node checks if evidence was retrieved via tools.
   - If no relevant evidence was found, triggers the deterministic fallback message:
     `"I don't have enough information in the available documents to answer this reliably."`
   - If evidence exists, attaches exact source file names and page numbers.

---

## 4. Vector Store Schema & Data Structures

```json
{
  "id": "sample_nda_p1_c0",
  "document": "1. Confidentiality Obligations. The Recipient shall maintain...",
  "embedding": [0.0381, -0.0129, 0.0894, "... 384 dimensions ..."],
  "metadata": {
    "chunk_id": "sample_nda_p1_c0",
    "doc_id": "sample_nda",
    "file_name": "sample_nda.pdf",
    "page_number": 1,
    "source_type": "native",
    "visibility": "shared"
  }
}
```

---

## 5. Key Design Principles

- **Zero-Hallucination Fallback**: Guarantees legal safety by returning a strict fallback message when no direct document evidence is retrieved.
- **In-Memory Model Caching**: Embedding model and Chroma client are loaded as cached singletons to eliminate per-request latency.
- **Self-Healing Vector Database**: Built-in migration and corruption recovery handles database restarts and schema transitions automatically.
- **Multi-Tenant Scoping**: Role-based access control filters chunks at retrieval time before reaching LLM context.
