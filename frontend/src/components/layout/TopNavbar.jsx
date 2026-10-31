import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Menu,
  Sun,
  Moon,
  LogOut,
  User as UserIcon,
  Activity,
  CheckCircle2,
  AlertCircle,
  ExternalLink,
} from 'lucide-react';
import { useAuth } from '../../context/AuthContext';
import { useTheme } from '../../context/ThemeContext';
import { checkBackendHealth } from '../../services/api';
import { Badge } from '../common/Badge';

export const TopNavbar = ({ onOpenMobileMenu }) => {
  const { user, logout, isDemoUser } = useAuth();
  const { theme, toggleTheme, isDark } = useTheme();
  const [userDropdownOpen, setUserDropdownOpen] = useState(false);

  // Poll backend health endpoint periodically with TanStack Query
  const { data: healthData, isSuccess, isError } = useQuery({
    queryKey: ['backendHealth'],
    queryFn: checkBackendHealth,
    refetchInterval: 15000,
    retry: 1,
  });

  const userEmail = user?.email || 'researcher@infoscope.ai';
  const userInitials = userEmail.slice(0, 2).toUpperCase();

  return (
    <header className="h-16 border-b border-slate-200 dark:border-slate-800/80 bg-white/80 dark:bg-slate-900/80 backdrop-blur-md sticky top-0 z-30 px-4 lg:px-8 flex items-center justify-between transition-colors">
      {/* Left: Mobile trigger & breadcrumb */}
      <div className="flex items-center gap-3">
        <button
          onClick={onOpenMobileMenu}
          aria-label="Open navigation menu"
          className="p-2 rounded-xl text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 lg:hidden"
        >
          <Menu className="w-5 h-5" />
        </button>

        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">
            Research Workspace
          </span>
          <span className="text-xs text-slate-400">/</span>
          <span className="text-xs font-medium text-slate-500 dark:text-slate-400">
            Information Gap Detection
          </span>
        </div>
      </div>

      {/* Right: Health Badge, Theme Toggle & User Profile */}
      <div className="flex items-center gap-3">
        {/* Backend API Health Status Indicator */}
        <div className="hidden sm:flex items-center">
          {isSuccess ? (
            <Badge variant="success" size="sm" dot title="FastAPI Backend Connected">
              <span className="hidden md:inline">API</span> v{healthData?.data?.version || '0.1.0'} Active
            </Badge>
          ) : isError ? (
            <Badge variant="warning" size="sm" dot title="FastAPI Backend is currently not detected on port 8000">
              <span className="hidden md:inline">API</span> Offline
            </Badge>
          ) : (
            <Badge variant="neutral" size="sm" dot>
              Checking API...
            </Badge>
          )}
        </div>

        {/* Theme Toggle Button */}
        <button
          onClick={toggleTheme}
          aria-label="Toggle dark/light theme"
          className="p-2 rounded-xl text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          title={`Switch to ${isDark ? 'Light' : 'Dark'} mode`}
        >
          {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-600" />}
        </button>

        {/* User Profile / Menu */}
        <div className="relative">
          <button
            onClick={() => setUserDropdownOpen(!userDropdownOpen)}
            className="flex items-center gap-2.5 p-1 pl-2 pr-2.5 rounded-xl border border-slate-200 dark:border-slate-800 hover:bg-slate-100 dark:hover:bg-slate-800/80 transition-colors"
          >
            <div className="w-7 h-7 rounded-lg bg-gradient-to-tr from-indigo-500 to-violet-500 flex items-center justify-center text-white text-xs font-semibold shadow-sm">
              {userInitials}
            </div>
            <div className="text-left hidden md:block">
              <p className="text-xs font-medium text-slate-800 dark:text-slate-200 max-w-[140px] truncate leading-tight">
                {userEmail}
              </p>
              <p className="text-[10px] text-slate-400 capitalize">
                {isDemoUser ? 'Demo Researcher' : 'Authenticated'}
              </p>
            </div>
          </button>

          {/* Dropdown Menu */}
          {userDropdownOpen && (
            <>
              <div
                className="fixed inset-0 z-30"
                onClick={() => setUserDropdownOpen(false)}
              />
              <div className="absolute right-0 mt-2 w-56 rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 shadow-xl z-40 py-2 animate-in fade-in zoom-in-95 duration-100">
                <div className="px-4 py-2 border-b border-slate-100 dark:border-slate-800">
                  <p className="text-xs text-slate-400">Signed in as</p>
                  <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 truncate mt-0.5">
                    {userEmail}
                  </p>
                  {isDemoUser && (
                    <span className="inline-block mt-1 text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/20">
                      Preview Session
                    </span>
                  )}
                </div>

                <div className="py-1">
                  <a
                    href="http://localhost:8000/docs"
                    target="_blank"
                    rel="noreferrer"
                    className="flex items-center justify-between px-4 py-2 text-xs text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
                  >
                    <span>FastAPI Swagger Docs</span>
                    <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
                  </a>
                </div>

                <div className="pt-1 border-t border-slate-100 dark:border-slate-800">
                  <button
                    onClick={() => {
                      setUserDropdownOpen(false);
                      logout();
                    }}
                    className="w-full flex items-center gap-2 px-4 py-2 text-xs font-medium text-rose-500 hover:bg-rose-500/10 transition-colors text-left"
                  >
                    <LogOut className="w-3.5 h-3.5" />
                    <span>Sign Out</span>
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </header>
  );
};
