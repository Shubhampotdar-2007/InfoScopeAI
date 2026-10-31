import React from 'react';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { Clock, ArrowLeft } from 'lucide-react';
import { Link } from 'react-router-dom';

export const PlaceholderPage = ({ title, description, icon: Icon }) => {
  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <Link
          to="/"
          className="inline-flex items-center gap-2 text-xs font-medium text-slate-500 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Dashboard</span>
        </Link>
        <Badge variant="warning" size="md">
          <Clock className="w-3.5 h-3.5 mr-1" /> Coming in Next Milestone
        </Badge>
      </div>

      <Card className="p-8 sm:p-12 text-center border-dashed border-2">
        <div className="w-14 h-14 rounded-2xl bg-indigo-500/10 dark:bg-indigo-950/60 border border-indigo-500/20 text-indigo-500 dark:text-indigo-400 mx-auto flex items-center justify-center mb-4">
          <Icon className="w-7 h-7" />
        </div>
        <h1 className="text-xl sm:text-2xl font-bold text-slate-900 dark:text-white tracking-tight">
          {title}
        </h1>
        <p className="max-w-md mx-auto text-sm text-slate-500 dark:text-slate-400 mt-2 leading-relaxed">
          {description}
        </p>
        <div className="mt-8 pt-6 border-t border-slate-200 dark:border-slate-800/80 flex items-center justify-center gap-3">
          <Link
            to="/"
            className="px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-sm transition-all"
          >
            Return to Dashboard
          </Link>
        </div>
      </Card>
    </div>
  );
};
