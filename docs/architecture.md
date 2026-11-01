# InfoScope AI — Architecture & System Design Specification

## 1. Executive Summary

**InfoScope AI** is an AI-assisted information gap detection platform. It accepts a research topic, concurrently collects intelligence from multiple search providers and user-targeted URLs, systematically normalizes claims, isolates contradictions and unbacked assertions, and compiles prioritized verification checklists.

This document outlines the system design across **Stage 1 (Foundation & Security)** and **Stage 2 (Multi-Provider Concurrent Web Research)**.

---

## 2. High-Level System Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                          Client Browser                                │
│   React 18 + Vite + Tailwind CSS v4 + TanStack Query + React Router   │
└──────────────────┬─────────────────────────────────┬───────────────────┘
                   │ HTTPS (Direct Supabase Auth)    │ REST / JSON (JWT Bearer)
                   ▼                                 ▼
┌──────────────────────────────────────┐  ┌──────────────────────────────┐
│       Supabase Managed Cloud         │  │   FastAPI Python Backend     │
│  - GoTrue Auth (Session / JWT)       │  │  - Uvicorn ASGI Server       │
│  - PostgreSQL with RLS               │  │  - Pydantic Settings & Models│
│  - research_sessions Table           │  │  - PyJWT Supabase Validator  │
│  - research_sources Table            │  │  - Health & Diagnostic APIs │
└──────────────────────────────────────┘  │  - Search Orchestrator       │
                   ▲                      └──────────────┬───────────────┘
                   │                                     │
                   │                                     ▼
                   │                           ┌──────────────┐
                   │                           │ Tavily Search│
                   │                           │   REST API   │
                   │                           └──────────────┘
                   │                                     │
                   └─────────────────────────────────────┴───────────────┘
```

---

## 3. Web Search Architecture (Tavily Sole Provider)

### 3.1 Search Provider
- **`TavilySearchProvider`**: Interacts with `https://api.tavily.com/search` to retrieve search results with content snippets and confidence scores.
- Reads `TAVILY_API_KEY` securely from the backend environment.
- Formats results into the normalized source schema (`NormalizedSource`).

### 3.2 Search Orchestration (`SearchOrchestrator`)
- Executes grounded search queries via `TavilySearchProvider`.
- Applies request timeouts capped via `TAVILY_TIMEOUT_SECONDS` (15s) and `SEARCH_TIMEOUT_SECONDS` (30s).
- Execution latency and status are recorded in `provider_statuses` for frontend diagnostics.

### 3.3 Normalization & Deduplication
- **`canonicalize_url`**: Normalizes schemes and hosts, removes default ports, collapses slashes, strips fragments (`#...`), and filters out tracking parameters (`utm_*`, `ref`, `fbclid`, etc.).
- **`merge_and_deduplicate_sources`**:
  - Groups items by canonical URL against any user-supplied target URLs.
  - Enforces `SEARCH_MAX_TOTAL_RESULTS` (default: 15).

### 3.4 Error Handling & Diagnostics
- Sanitizes error messages to protect credentials and internal endpoints.
- Classifies errors cleanly into timeouts, authentication issues, rate limits, and API errors.

---

## 4. Security Architecture

### Zero-Trust Authentication
1. **No Client-Supplied User IDs in Request Bodies**: The backend derives user identity strictly from the verified JWT `sub` claim.
2. **Cryptographic JWT Verification**: PyJWT verifies access tokens against `SUPABASE_JWT_SECRET` (HS256) and audience `authenticated`.
3. **Secret Isolation**: `TAVILY_API_KEY` resides exclusively in `backend/.env` and is never exposed to browser bundles.

### Database Row Level Security (RLS)
PostgreSQL enforces user isolation across all tables:
- `research_sessions`: `USING (auth.uid() = user_id)`
- `research_sources`: `USING (auth.uid() = user_id)`

---

## 5. API Endpoints

| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Public | Service metadata & documentation links |
| `GET` | `/api/v1/health` | Public | System uptime & health status |
| `GET` | `/api/v1/research/sessions` | Protected (JWT) | Lists user's research sessions |
| `POST` | `/api/v1/research/sessions` | Protected (JWT) | Ingests research query, executes Tavily search, and returns normalized sources |

---

## 6. Roadmap & Next Phases

1. **Stage 1 (Done)**: Production foundation, Supabase Auth, RLS, Tailwind v4 Dashboard.
2. **Stage 2 (Done)**: Tavily web search, normalization, deduplication, and attribution.
3. **Stage 3 (Next)**: Sentence-level claim extraction pipeline.
4. **Stage 4 (Next)**: Contradiction detection & information gap classifier.
5. **Stage 5 (Next)**: Evidence-backed report synthesis and verification checklist generation.
