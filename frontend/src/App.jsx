import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider } from './context/AuthContext';
import { ThemeProvider } from './context/ThemeContext';
import { ProtectedRoute } from './components/auth/ProtectedRoute';
import { AppLayout } from './components/layout/AppLayout';
import { DashboardPage } from './pages/DashboardPage';
import { AuthPage } from './pages/AuthPage';
import { PlaceholderPage } from './pages/PlaceholderPage';
import {
  Sparkles,
  Globe2,
  AlertTriangle,
  CheckSquare,
  History,
} from 'lucide-react';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 1000 * 30, // 30 seconds
      refetchOnWindowFocus: false,
    },
  },
});

export const App = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <AuthProvider>
          <BrowserRouter>
            <Routes>
              {/* Public Authentication Route */}
              <Route path="/login" element={<AuthPage />} />

              {/* Protected App Routes */}
              <Route
                path="/"
                element={
                  <ProtectedRoute>
                    <AppLayout />
                  </ProtectedRoute>
                }
              >
                {/* 1. Dashboard (Active MVP) */}
                <Route index element={<DashboardPage />} />

                {/* 2. New Research (Coming Soon) */}
                <Route
                  path="research/new"
                  element={
                    <PlaceholderPage
                      title="Autonomous Research Engine"
                      description="Deep crawling, web search orchestration, and automated evidence aggregation pipelines will be unlocked here."
                      icon={Sparkles}
                    />
                  }
                />

                {/* 3. Sources (Coming Soon) */}
                <Route
                  path="sources"
                  element={
                    <PlaceholderPage
                      title="Source & Citation Manager"
                      description="Connect custom URLs, RSS feeds, API documents, and track source authority and freshness scores."
                      icon={Globe2}
                    />
                  }
                />

                {/* 4. Detected Issues (Coming Soon) */}
                <Route
                  path="issues"
                  element={
                    <PlaceholderPage
                      title="Claim Discrepancy & Conflict Hub"
                      description="Detailed timeline analysis showing where claims diverge, conflicting metric values, and outdated statements."
                      icon={AlertTriangle}
                    />
                  }
                />

                {/* 5. Verification Checklist (Coming Soon) */}
                <Route
                  path="checklist"
                  element={
                    <PlaceholderPage
                      title="Prioritized Verification Checklist"
                      description="Actionable, evidence-backed tasks for human researchers to follow up on unresolved gaps and contradictions."
                      icon={CheckSquare}
                    />
                  }
                />

                {/* 6. Research History (Coming Soon) */}
                <Route
                  path="history"
                  element={
                    <PlaceholderPage
                      title="Research Session Archives"
                      description="Browse, export, and search historical gap detection investigations stored in Supabase PostgreSQL."
                      icon={History}
                    />
                  }
                />
              </Route>

              {/* Fallback */}
              <Route path="*" element={<Navigate to="/" replace />} />
            </Routes>
          </BrowserRouter>
        </AuthProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
};

export default App;
