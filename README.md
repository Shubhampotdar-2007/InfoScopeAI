# InfoScope AI — AI Information Gap Detection Platform

**InfoScope AI** is a multi-source research and information analysis platform designed to accept complex investigation topics, systematically collect intelligence from web search (powered solely by Tavily) and user-supplied URLs, track critical expected research dimensions, and calculate real-time coverage completeness scores.

The platform is designed with a zero-trust multi-tenant security architecture: all user database operations are authenticated using cryptographic ES256 Supabase JWT verification against project JWKS, forwarding user tokens to Supabase PostgREST with strict Row Level Security (RLS).

---

## 🚀 Key Features

- **Grounded Web Intelligence Retrieval**: Leverages the Tavily Search API as the sole web retrieval engine for real-time, high-signal research sources.
- **URL Canonicalization & Deduplication**: Normalizes URLs (stripping tracking parameters, default ports, anchors) to deduplicate sources across search queries and custom target URLs.
- **Provider Attribution Diagnostics**: Measures retrieval latency and source counts with clear non-sensitive diagnostics for timeouts or network issues.
- **Expected Research Dimensions**: Define and customize weighted evaluation criteria (e.g., Architecture, Pricing, Security, Performance) with relative importance weights (0.10x to 5.00x).
- **Mathematical Coverage Scoring**: Real-time completeness calculation:
  $$\text{Coverage Score} = \text{round}\left(\frac{\sum (\text{weight} \times \text{status\_factor})}{\sum \text{weight}} \times 100\right)$$
  *(Covered = 1.0 factor, Partially Covered = 0.5 factor, Missing = 0.0 factor)*.
- **Full Historical Archive**: Browse, reopen, inspect, and update previous research sessions persisted with PostgreSQL RLS isolation.
- **Zero-Trust Security**: Authenticated requests derive user identity strictly from verified Supabase ES256 JWT tokens. Never accepts unverified frontend user IDs.
- **Autonomous Claims & Conflict Hub**: Clearly designated as in active development, maintaining absolute data integrity without fabricating synthetic claims.

---

## 🛠️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 18, Vite 6, Tailwind CSS v4, React Router DOM v6, TanStack React Query v5, Axios, Lucide React, Recharts |
| **Backend** | Python 3.12+ (tested on Python 3.14.7), FastAPI, Uvicorn, Pydantic V2, Pydantic Settings, HTTPX, PyJWT, Cryptography |
| **Database & Auth** | Supabase Auth (GoTrue), Supabase PostgreSQL 15, PostgREST v1, Row Level Security (RLS) |
| **Search Engine** | **Tavily Search API** (grounded real-time web retrieval) |

---

## 📁 Repository Structure

```
InfoScope-AI/
├── frontend/
│   ├── public/
│   │   └── vite.svg
│   ├── src/
│   │   ├── assets/
│   │   │   └── logo.svg
│   │   ├── components/
│   │   │   ├── auth/
│   │   │   │   └── ProtectedRoute.jsx
│   │   │   ├── common/
│   │   │   │   ├── Badge.jsx
│   │   │   │   └── Card.jsx
│   │   │   └── layout/
│   │   │       ├── AppLayout.jsx
│   │   │       ├── Sidebar.jsx
│   │   │       └── TopNavbar.jsx
│   │   ├── context/
│   │   │   ├── AuthContext.jsx
│   │   │   └── ThemeContext.jsx
│   │   ├── hooks/
│   │   │   └── useResearchSession.js
│   │   ├── lib/
│   │   │   └── supabaseClient.js
│   │   ├── pages/
│   │   │   ├── AuthPage.jsx
│   │   │   ├── DashboardPage.jsx
│   │   │   └── PlaceholderPage.jsx
│   │   ├── services/
│   │   │   └── api.js
│   │   ├── utils/
│   │   │   ├── searchErrors.js
│   │   │   └── searchErrors.test.js
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   └── index.css
│   ├── .env.example
│   ├── package.json
│   └── vite.config.js
├── backend/
│   ├── app/
│   │   ├── api/
│   │   │   ├── routes/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── health.py
│   │   │   │   └── research.py
│   │   │   └── __init__.py
│   │   ├── core/
│   │   │   ├── __init__.py
│   │   │   ├── config.py
│   │   │   └── security.py
│   │   ├── database/
│   │   │   ├── repositories/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py
│   │   │   │   ├── checklist.py
│   │   │   │   ├── claims.py
│   │   │   │   ├── expected_fields.py
│   │   │   │   ├── issue_evidence.py
│   │   │   │   ├── issues.py
│   │   │   │   ├── reports.py
│   │   │   │   ├── sessions.py
│   │   │   │   └── sources.py
│   │   │   ├── client.py
│   │   │   ├── exceptions.py
│   │   │   └── __init__.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── health.py
│   │   │   ├── research.py
│   │   │   └── response.py
│   │   ├── services/
│   │   │   ├── search/
│   │   │   │   ├── __init__.py
│   │   │   │   ├── base.py            # NormalizedSource & BaseSearchProvider ABC
│   │   │   │   ├── normalizer.py      # Canonicalization & deduplication
│   │   │   │   ├── orchestrator.py    # Search runner
│   │   │   │   └── tavily.py          # Tavily search API provider
│   │   │   └── __init__.py
│   │   ├── main.py
│   │   └── __init__.py
│   ├── scripts/
│   │   └── verify_tavily_live.py
│   ├── tests/
│   │   ├── conftest.py
│   │   ├── test_analysis_repositories.py
│   │   ├── test_auth_audit.py
│   │   ├── test_core_repositories.py
│   │   ├── test_database_foundation.py
│   │   ├── test_expected_fields_api.py
│   │   ├── test_health.py
│   │   ├── test_jwt_alg_regression.py
│   │   ├── test_research_sessions_api.py
│   │   └── test_search_providers.py
│   ├── .env.example
│   └── requirements.txt
├── database/
│   ├── migrations/
│   │   ├── 001_initial_schema.sql
│   │   └── 002_stage3_schema_expansion.sql
│   ├── tests/
│   │   └── test_stage3_migration.sql
│   └── schema.sql
├── docs/
│   └── architecture.md
├── .gitignore
└── README.md
```

---

## ⚡ Prerequisites

- **Node.js**: v18.0.0+ (Tested with Node v24+)
- **Python**: 3.12+ (Tested with Python 3.14.7)
- **Supabase Account**: A free Supabase project from [supabase.com](https://supabase.com)
- **Tavily Search API Key**: Available at [tavily.com](https://tavily.com)

---

## 🔑 Environment Configuration

Create local environment files from the provided templates:

### 1. Backend (`backend/.env`)
```bash
PROJECT_NAME="InfoScope AI"
API_V1_STR="/api/v1"
ENVIRONMENT="development"
DEBUG=True
HOST="0.0.0.0"
PORT=8000
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173","http://localhost:3000"]

# Supabase Configuration (Settings -> API)
SUPABASE_URL="https://your-project-ref.supabase.co"
SUPABASE_ANON_KEY="your-supabase-anon-key"
SUPABASE_KEY=""
SUPABASE_SERVICE_ROLE_KEY=""
SUPABASE_JWT_AUDIENCE="authenticated"
SUPABASE_JWT_ALGORITHM="ES256"

# Tavily Search Provider
TAVILY_API_KEY="tvly-your-api-key"
SEARCH_TIMEOUT_SECONDS=30.0
TAVILY_TIMEOUT_SECONDS=15.0
SEARCH_MAX_RESULTS_PER_PROVIDER=5
SEARCH_MAX_TOTAL_RESULTS=15
```

### 2. Frontend (`frontend/.env`)
```bash
VITE_SUPABASE_URL=https://your-project-ref.supabase.co
VITE_SUPABASE_ANON_KEY=your-supabase-anon-key
VITE_API_BASE_URL=http://localhost:8000
```

> **Security Note:** Never commit `.env` files or share API keys, JWT secrets, or Supabase service-role credentials. `.env` is excluded in `.gitignore`.

---

## 🗄️ Database Setup & Migrations

To apply or verify the Supabase PostgreSQL database schema:

1. Open your project at [Supabase Dashboard](https://supabase.com/dashboard).
2. Go to **SQL Editor** in the left sidebar.
3. Run the schema migrations in order:
   - **Migration 001**: [`database/migrations/001_initial_schema.sql`](database/migrations/001_initial_schema.sql) — Sets up `research_sessions` and `research_sources` with user isolation and RLS policies.
   - **Migration 002**: [`database/migrations/002_stage3_schema_expansion.sql`](database/migrations/002_stage3_schema_expansion.sql) — Atomically creates `expected_fields`, `claims`, `issues`, `issue_evidence`, `checklist_items`, and `reports` with composite FKs and strict RLS policies.

To verify schema integrity:
- Run [`database/tests/test_stage3_migration.sql`](database/tests/test_stage3_migration.sql) inside Supabase SQL Editor. The test runs in a transaction and rolls back automatically.

---

## 🚀 Running the Application Locally

### 1. Start the Backend API Server
```powershell
# Navigate to project root
$env:PYTHONPATH="backend"
.\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000
```
- API Base: `http://localhost:8000`
- Interactive Swagger UI: `http://localhost:8000/docs`
- Health Check: `http://localhost:8000/api/v1/health`

### 2. Start the Frontend Application
```powershell
# In a separate terminal
cd frontend
npm.cmd run dev
```
- Web Application: `http://localhost:5173`

---

## 🧪 Testing and Verification

### Backend Regression Tests
Run the complete Pytest suite (115 passed):
```powershell
$env:PYTHONPATH="backend"
.\backend\.venv\Scripts\pytest backend\tests -v
```

**Test Suites**:
- `test_analysis_repositories.py`: Repositories for claims, issues, checklist, reports (10 passed)
- `test_auth_audit.py`: User isolation, token rejection, RLS verification (5 passed)
- `test_core_repositories.py`: Sessions and sources repositories (13 passed)
- `test_database_foundation.py`: PostgREST client, error mapping, connection pooling (24 passed)
- `test_expected_fields_api.py`: Expected fields CRUD, weight constraints, coverage calculation (14 passed)
- `test_health.py`: Health endpoint and root info (3 passed)
- `test_jwt_alg_regression.py`: ES256 JWKS cryptographic validation (10 passed)
- `test_research_sessions_api.py`: Research API routes, session lifecycle, source persistence (23 passed)
- `test_search_providers.py`: Tavily provider, URL canonicalization, deduplication (13 passed)

### Frontend Verification
```powershell
# 1. Run Search Error Unit Tests
node --test frontend/src/utils/searchErrors.test.js

# 2. Run Production Build
cd frontend
npm.cmd run build
```

---

## 🎬 Demonstration Flow

1. **Sign Up / Sign In**: Access `http://localhost:5173` and authenticate with email/password via Supabase Auth.
2. **Formulate Investigation**: Enter a research query (e.g., *"Compare Supabase Auth vs AWS Cognito architecture in 2026"*). Select search strategy (Web Search / Both).
3. **Trigger Analysis**: Click **Analyze Information Gaps**. Tavily executes web retrieval and normalizes sources.
4. **Inspect Sources**: Review retrieved sources with canonical URLs, relevance scores, and direct external links.
5. **Add Expected Dimensions**: Add custom dimensions or click **Load Starter Criteria** to add evaluation criteria with assigned weights.
6. **Coverage Analytics**: Review the Coverage Dashboard displaying the mathematical completeness percentage, criteria breakdown, and category depth chart.
7. **Research History**: Return to the dashboard and review previous sessions. Click any historical session to reopen it.

---

## ⚠️ Known Limitations

1. **Autonomous Claim Extraction**: LLM-based claim extraction and claim conflict cross-referencing are in active development. This MVP strictly relies on verified web sources and criteria evaluation without fabricating synthetic claims.
2. **PostgREST User Scope**: Normal user database queries strictly use the verified user's JWT with Supabase anon key headers. The service-role key is never used for ordinary database operations.
3. **Web Search**: Tavily Search is the sole web provider. If Tavily rate limits or credentials are not configured, clear non-sensitive diagnostics are surfaced.
