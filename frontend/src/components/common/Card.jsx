import React from 'react';

export const Card = ({
  children,
  className = '',
  hover = false,
  glow = false,
  onClick,
}) => {
  return (
    <div
      onClick={onClick}
      className={`
        rounded-2xl transition-all duration-200 border
        bg-white dark:bg-slate-900/90 
        border-slate-200 dark:border-slate-800/80
        shadow-sm dark:shadow-none
        ${hover ? 'hover:border-indigo-500/50 hover:shadow-md dark:hover:border-indigo-500/40 hover:-translate-y-0.5' : ''}
        ${glow ? 'relative before:absolute before:-inset-0.5 before:bg-gradient-to-r before:from-indigo-500 before:to-violet-500 before:rounded-2xl before:blur-sm before:opacity-20 before:-z-10' : ''}
        ${className}
      `}
    >
      {children}
    </div>
  );
};
