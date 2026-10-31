import React from 'react';

export const Badge = ({
  children,
  variant = 'neutral',
  size = 'md',
  dot = false,
  className = '',
}) => {
  const sizeClasses = {
    sm: 'text-xs px-2 py-0.5',
    md: 'text-xs px-2.5 py-1',
    lg: 'text-sm px-3 py-1.5',
  };

  const variantClasses = {
    primary: 'bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 dark:bg-indigo-950/50 dark:text-indigo-300 dark:border-indigo-800/60',
    success: 'bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 dark:bg-emerald-950/50 dark:text-emerald-300 dark:border-emerald-800/60',
    warning: 'bg-amber-500/10 text-amber-400 border border-amber-500/20 dark:bg-amber-950/50 dark:text-amber-300 dark:border-amber-800/60',
    danger: 'bg-rose-500/10 text-rose-400 border border-rose-500/20 dark:bg-rose-950/50 dark:text-rose-300 dark:border-rose-800/60',
    info: 'bg-blue-500/10 text-blue-400 border border-blue-500/20 dark:bg-blue-950/50 dark:text-blue-300 dark:border-blue-800/60',
    neutral: 'bg-slate-500/10 text-slate-400 border border-slate-500/20 dark:bg-slate-800/60 dark:text-slate-300 dark:border-slate-700/60',
  };

  const dotClasses = {
    primary: 'bg-indigo-400',
    success: 'bg-emerald-400 animate-pulse',
    warning: 'bg-amber-400',
    danger: 'bg-rose-400',
    info: 'bg-blue-400',
    neutral: 'bg-slate-400',
  };

  return (
    <span
      className={`inline-flex items-center gap-1.5 font-medium rounded-full ${sizeClasses[size]} ${variantClasses[variant]} ${className}`}
    >
      {dot && <span className={`w-1.5 h-1.5 rounded-full ${dotClasses[variant]}`} />}
      {children}
    </span>
  );
};
