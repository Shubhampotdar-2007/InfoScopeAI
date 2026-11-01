import React from 'react';
import { NavLink } from 'react-router-dom';
import {
  LayoutDashboard,
  Sparkles,
  Globe2,
  AlertTriangle,
  CheckSquare,
  History,
  ShieldCheck,
  ChevronRight,
  Database,
  SearchCode,
} from 'lucide-react';
import { Badge } from '../common/Badge';

export const Sidebar = ({ isOpen, onClose }) => {
  const navItems = [
    {
      to: '/',
      label: 'Dashboard',
      icon: LayoutDashboard,
      status: null,
      exact: true,
    },
    {
      to: '/research/new',
      label: 'New Research',
      icon: Sparkles,
      status: null,
    },
    {
      to: '/history',
      label: 'Research History',
      icon: History,
      status: null,
    },
    {
      to: '/sources',
      label: 'Sources',
      icon: Globe2,
      status: 'Coming Soon',
    },
    {
      to: '/issues',
      label: 'Detected Issues',
      icon: AlertTriangle,
      status: 'Coming Soon',
    },
    {
      to: '/checklist',
      label: 'Verification Checklist',
      icon: CheckSquare,
      status: 'Coming Soon',
    },
  ];

  return (
    <>
      {/* Mobile Backdrop */}
      {isOpen && (
        <div
          onClick={onClose}
          className="fixed inset-0 bg-slate-950/60 backdrop-blur-sm z-40 lg:hidden"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`
          fixed top-0 bottom-0 left-0 z-50 w-64 flex flex-col
          bg-slate-900 border-r border-slate-800/80
          text-slate-300 transition-transform duration-300 ease-in-out
          lg:static lg:translate-x-0
          ${isOpen ? 'translate-x-0' : '-translate-x-full'}
        `}
      >
        {/* Branding Header */}
        <div className="h-16 flex items-center px-6 border-b border-slate-800/80 gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
            <SearchCode className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="font-bold text-lg text-white tracking-tight">InfoScope</span>
              <span className="text-xs font-semibold px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">AI</span>
            </div>
            <p className="text-[10px] text-slate-400 tracking-wide uppercase font-medium">Gap Detection Engine</p>
          </div>
        </div>

        {/* Navigation Items */}
        <nav className="flex-1 overflow-y-auto px-3 py-4 space-y-1">
          <div className="px-3 pb-2 text-[11px] font-semibold tracking-wider text-slate-400 uppercase">
            Platform
          </div>

          {navItems.map((item) => {
            const Icon = item.icon;
            return (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.exact}
                onClick={onClose}
                className={({ isActive }) => `
                  flex items-center justify-between px-3 py-2.5 rounded-xl text-sm font-medium transition-all group
                  ${isActive
                    ? 'bg-gradient-to-r from-indigo-600/90 to-indigo-600/70 text-white shadow-sm shadow-indigo-600/30'
                    : 'text-slate-400 hover:text-slate-100 hover:bg-slate-800/60'
                  }
                `}
              >
                <div className="flex items-center gap-3">
                  <Icon className="w-4 h-4 transition-colors" />
                  <span>{item.label}</span>
                </div>
                {item.status ? (
                  <Badge variant="neutral" size="sm" className="text-[10px] py-0 px-1.5 bg-slate-800 text-slate-400 border-slate-700/60">
                    {item.status}
                  </Badge>
                ) : (
                  <ChevronRight className="w-3.5 h-3.5 opacity-0 group-hover:opacity-100 transition-opacity" />
                )}
              </NavLink>
            );
          })}
        </nav>

        {/* System Capabilities Footer Card */}
        <div className="p-3 border-t border-slate-800/80">
          <div className="p-3 rounded-xl bg-slate-800/40 border border-slate-800 flex flex-col gap-2">
            <div className="flex items-center gap-2 text-xs font-medium text-slate-300">
              <ShieldCheck className="w-4 h-4 text-emerald-400" />
              <span>Multi-Source Verification</span>
            </div>
            <p className="text-[11px] text-slate-400 leading-relaxed">
              Detects gaps, conflicting claims, and source staleness across web intelligence.
            </p>
            <div className="flex items-center justify-between pt-1 border-t border-slate-800 text-[10px] text-slate-400">
              <span className="flex items-center gap-1">
                <Database className="w-3 h-3 text-indigo-400" /> Supabase RLS
              </span>
              <span>v0.1.0 MVP</span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
};
