# InfoScope AI — Information Gap Detection Platform

**InfoScope AI** is an AI-assisted information gap detection platform designed to accept a research topic or question, systematically collect intelligence from web search and targeted URLs, extract and cross-examine claims, isolate contradictions and information gaps, and compile prioritized verification checklists.

This repository contains the **initial production-minded MVP foundation**, including a React/Vite/Tailwind CSS v4 frontend, a FastAPI Python 3.12+ backend, and a Supabase PostgreSQL schema with Row Level Security (RLS).

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
│   │   │   └── __init__.py
│   │   ├── schemas/
│   │   │   ├── __init__.py
│   │   │   ├── health.py
│   │   │   ├── research.py
│   │   │   └── response.py
│   │   ├── services/
│   │   │   └── __init__.py
│   │   ├── main.py
│   │   └── __init__.py
│   ├── tests/
│   │   ├── __init__.py
│   │   └── test_health.py
│   ├── .env.example
│   └── requirements.txt
├── database/
│   └── schema.sql
├── docs/
│   └── architecture.md
├── .gitignore
└── README.md
```

---

## 🛠️ Technology Stack

| Layer | Technologies |
| :--- | :--- |
| **Frontend** | React 18, Vite, Tailwind CSS v4, React Router DOM, Supabase JS SDK, TanStack Query, Axios, Lucide React, Recharts |
| **Backend** | Python 3.12+ (tested on Python 3.14), FastAPI, Uvicorn, Pydantic V2, Pydantic Settings, HTTPX, PyJWT |
| **Database & Auth** | Supabase Authentication (GoTrue), Supabase PostgreSQL, Row Level Security (RLS) |

---

## ⚡ Quick Start Guide (Windows PowerShell)

### 1. Prerequisites
- **Node.js**: v18.0.0+ (Tested with Node v24.21.0 & npm 11.19.0)
- **Python**: 3.12+ (Tested with Python 3.14.7)
- **Supabase Account**: A free Supabase project from [supabase.com](https://supabase.com)

---

### 2. Backend Setup & Run

Open a Windows PowerShell terminal in the repository root:

```powershell
# 1. Create Python virtual environment (if not already created)
python -m venv backend\.venv

# 2. Activate virtual environment
.\backend\.venv\Scripts\Activate.ps1

# 3. Upgrade pip and install dependencies
pip install -r backend\requirements.txt

# 4. Create your backend environment configuration
Copy-Item backend\.env.example backend\.env

# 5. Run the FastAPI backend development server
uvicorn app.main:app --app-dir backend --reload --host 0.0.0.0 --port 8000
```

> **Tip:** If PowerShell displays an execution policy restriction when activating the venv, you can run directly via the venv python executable:
> ```powershell
> .\backend\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --reload --port 8000
> ```

---

### 3. Frontend Setup & Run

Open a second Windows PowerShell terminal in the repository root:

```powershell
# 1. Navigate to the frontend directory
cd frontend

# 2. Install npm dependencies
npm.cmd install

# 3. Create your frontend environment configuration
Copy-Item .env.example .env

# 4. Start the Vite development server
npm.cmd run dev
```

The frontend will be available at: **`http://localhost:5173`**

---

### 4. Database Setup (Supabase SQL)

1. Open your project on the [Supabase Dashboard](https://supabase.com/dashboard).
2. Click on **SQL Editor** in the left sidebar.
3. Open [`database/schema.sql`](database/schema.sql), copy its contents, paste them into the SQL Editor, and click **Run**.

This script sets up:
- The `public.research_sessions` table with foreign key to `auth.users(id)`.
- Row Level Security (RLS) enabled on `research_sessions`.
- 4 granular RLS policies ensuring users can only read, insert, update, and delete their own sessions.
- An automatic trigger updating the `updated_at` column.
- Optimized performance indexes.

---

## 🔑 Environment Variables Reference

### Frontend Configuration (`frontend/.env`)

| Variable | Description | Example Value |
| :--- | :--- | :--- |
| `VITE_SUPABASE_URL` | Your Supabase project URL | `https://xyzproject.supabase.co` |
| `VITE_SUPABASE_ANON_KEY` | Supabase publishable anonymous key | `eyJhbGciOiJIUzI1Ni...` |
| `VITE_API_BASE_URL` | Backend FastAPI service base URL | `http://localhost:8000` |

> **Note on Demo Mode:** If Supabase keys are not configured yet, the frontend will display a notice and provide an **"Instant Demo Preview"** button on the login screen so you can immediately explore and test the dashboard.

### Backend Configuration (`backend/.env`)

| Variable | Description | Default / Example |
| :--- | :--- | :--- |
| `PROJECT_NAME` | Service name | `InfoScope AI` |
| `API_V1_STR` | API route prefix | `/api/v1` |
| `ENVIRONMENT` | Environment name | `development` |
| `DEBUG` | Verbose debug mode | `True` |
| `HOST` | Bind address | `0.0.0.0` |
| `PORT` | Server port | `8000` |
| `CORS_ORIGINS` | Allowed client origins | `["http://localhost:5173","http://127.0.0.1:5173"]` |
| `SUPABASE_URL` | Supabase project URL | `https://xyzproject.supabase.co` |
| `SUPABASE_JWT_SECRET` | Supabase JWT Secret for token verification | *(From Supabase Project Settings -> API)* |
| `SUPABASE_JWT_AUDIENCE` | Token audience | `authenticated` |
| `SUPABASE_JWT_ALGORITHM`| Token signature algorithm | `HS256` |

---

## 🧪 Testing and Verification

### Backend Verification (Pytest)
Run all backend integration tests:

```powershell
.\backend\.venv\Scripts\pytest.exe backend\tests -v
```

All 3 tests verify:
- `GET /`: API welcome and documentation link envelope.
- `GET /api/v1/health`: Uptime, service version, environment metadata, and proper health response.
- Protected route security: Ensuring unauthorized requests without a valid Supabase JWT Bearer token return `401 Unauthorized`.

### Frontend Build Verification
Verify production bundling:

```powershell
cd frontend
npm.cmd run build
```

---

## 🌐 Localhost URLs & Endpoints

| Service | URL | Notes |
| :--- | :--- | :--- |
| **Frontend Application** | `http://localhost:5173` | React Dashboard & Auth UI |
| **Backend API Root** | `http://localhost:8000/` | Service metadata & links |
| **Backend Health Check** | `http://localhost:8000/api/v1/health` | Public service liveness & uptime |
| **Swagger Interactive Docs** | `http://localhost:8000/docs` | Interactive OpenAPI documentation |
| **ReDoc Documentation** | `http://localhost:8000/redoc` | Formatted API documentation |

---

## 🔒 Security Summary

1. **Zero Trust for Request Body User IDs**: User identities are resolved strictly by verifying the Supabase JWT Bearer token on the backend.
2. **Database RLS Enforced**: Access policies are enforced by PostgreSQL at the database level.
3. **Environment Segregation**: Sensitive credentials (e.g. JWT secret, future LLM keys) are never exposed to the client bundle.
4. **Health Endpoint Liveness**: The `/api/v1/health` endpoint serves strictly as an operational probe and does not claim to authenticate users.
