# InfoScope AI — Architecture & System Design Specification

## 1. Executive Summary

**InfoScope AI** is an AI-assisted information gap detection platform. It is engineered to accept a research topic, ingest both live web intelligence and user-targeted URLs, systematically extract and cross-examine claims, isolate contradictions and unbacked assertions, and synthesize prioritized verification checklists with coverage scores.

This document outlines the foundation architecture, security perimeter, data flows, and component interactions established in the initial production-minded MVP.

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
└──────────────────────────────────────┘  │  - Health & Diagnostic APIs │
                   ▲                      └──────────────┬───────────────┘
                   │                                     │
                   └─────────────────────────────────────┘
                     Async Pipeline & Server Verification
```

---

## 3. Technology Stack Breakdown

### Frontend Tier
- **Framework**: React 18 with Vite.
- **Language**: JavaScript (ES2023+).
- **Styling**: Tailwind CSS v4 with modern CSS variables, supporting a hybrid dark/light theme (default: Dark Navy `#0b0f19`).
- **State & Server Cache**: TanStack Query v5 with optimistic caching and health polling.
- **Routing**: React Router DOM v6 with protected route wrappers (`ProtectedRoute.jsx`).
- **Icons**: Lucide React.
- **Visualization**: Recharts for coverage distribution, claim status breakdowns, and metrics.
- **API Client**: Axios configured with auto-injection of Supabase Bearer tokens.

### Backend Tier
- **Runtime**: Python 3.12+ (tested on Python 3.14).
- **Framework**: FastAPI (high-performance async ASGI).
- **Server**: Uvicorn with ASGI transport.
- **Configuration**: Pydantic Settings with strict validation and `.env` loading.
- **Security & JWT**: PyJWT with cryptography for server-side Supabase token verification.
- **HTTP Client**: HTTPX for async external requests and testing.
- **Validation**: Pydantic V2 models for strict request/response contracts.
- **Documentation**: Automatic OpenAPI 3.1 Swagger UI (`/docs`) and ReDoc (`/redoc`).

### Database & Auth Tier
- **Authentication**: Supabase Auth (GoTrue) handling email/password signup, session storage, and JWT token issuance.
- **Persistence**: Supabase PostgreSQL.
- **Access Control**: Row Level Security (RLS) guaranteeing that queries and mutations are isolated to `auth.uid() = user_id`.

---

## 4. Security Architecture

### Zero-Trust Authentication
1. **No Client-Supplied User IDs in Request Bodies**: The backend does NOT accept or trust a `user_id` supplied in request payloads to identify who is making a request.
2. **Cryptographic JWT Verification**: In incoming requests, the Bearer token in the `Authorization` header is verified against `SUPABASE_JWT_SECRET`. The authenticated user ID is extracted strictly from the token's `sub` claim.
3. **Fail-Closed Strategy**: If credentials are missing, expired, or malformed, a standardized `401 Unauthorized` response is returned.

### Row Level Security (RLS)
The database enforces tenant isolation at the PostgreSQL engine level:
```sql
ALTER TABLE public.research_sessions ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Users can view own research sessions"
    ON public.research_sessions FOR SELECT
    USING (auth.uid() = user_id);
```
Even if a developer makes an error in backend filtering, PostgreSQL will never return records belonging to another `user_id`.

### Secret Segregation
- **Browser-Safe Variables**: Only public configuration is exposed to Vite via `VITE_` prefixes (`VITE_SUPABASE_URL`, `VITE_SUPABASE_ANON_KEY`, `VITE_API_BASE_URL`).
- **Backend Secrets**: Supabase service role keys, JWT secrets, and future LLM API keys reside strictly on the server in `backend/.env`.

---

## 5. Standardized API Protocol

All backend endpoints adhere to a unified JSON envelope:

```json
{
  "success": true,
  "status_code": 200,
  "message": "InfoScope AI backend is operational.",
  "data": { ... },
  "timestamp": "2026-10-31T06:50:00.000000Z"
}
```

### Initial Core Endpoints
| Method | Endpoint | Access | Purpose |
| :--- | :--- | :--- | :--- |
| `GET` | `/` | Public | Service metadata, version, and documentation links |
| `GET` | `/api/v1/health` | Public | System uptime, environment status, and health metrics |
| `GET` | `/api/v1/research/sessions` | Protected (JWT) | Lists research sessions owned by authenticated user |
| `POST` | `/api/v1/research/sessions` | Protected (JWT) | Validates research query and initiates gap analysis pipeline |

*Note: As per requirements, the `/api/v1/health` endpoint serves strictly as a liveness probe and does not perform user authentication.*

---

## 6. Frontend Navigation & Module Blueprint

| Navigation Item | Route | Status | Description |
| :--- | :--- | :--- | :--- |
| **Dashboard** | `/` | Active (MVP) | Research query input, source strategy toggle (Web, My URLs, Both), feature pillars, coverage charts, sample preview mode |
| **New Research** | `/research/new` | Coming Soon | Dedicated deep-crawling configuration workspace |
| **Sources** | `/sources` | Coming Soon | URL collection, RSS/API connectors, authority scoring |
| **Detected Issues** | `/issues` | Coming Soon | Side-by-side claim conflict analyzer & timeline diff |
| **Verification Checklist** | `/checklist` | Coming Soon | Prioritized action items for researcher verification |
| **Research History** | `/history` | Coming Soon | Searchable archive of completed gap investigations |

---

## 7. Roadmap & Next Phases

1. **Phase 2 — Ingestion & Search Engine**: Integrate web search APIs (e.g. Brave / Tavily / Serper) and secure asynchronous URL crawling with strict SSRF protection.
2. **Phase 3 — Claim Extraction Pipeline**: Parse ingested HTML/text, extract factual claims with sentence-level citations.
3. **Phase 4 — Gap & Discrepancy Classifier**: LLM-driven cross-comparison to detect contradictory claims and uncorroborated gaps.
4. **Phase 5 — Report Synthesis**: Automatic generation of verification checklists and PDF/Markdown audit exports.
