import React, { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';
import { useTheme } from '../context/ThemeContext';
import {
  SearchCode,
  Lock,
  Mail,
  ArrowRight,
  Loader2,
  AlertCircle,
  CheckCircle2,
  KeyRound,
  Sparkles,
  Sun,
  Moon,
  Info,
} from 'lucide-react';

export const AuthPage = () => {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [localError, setLocalError] = useState('');
  const [successMessage, setSuccessMessage] = useState('');

  const { login, register, loginDemoUser, isConfigured } = useAuth();
  const { isDark, toggleTheme } = useTheme();
  const navigate = useNavigate();
  const location = useLocation();

  const from = location.state?.from?.pathname || '/';

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLocalError('');
    setSuccessMessage('');

    if (!email || !password) {
      setLocalError('Please enter both email and password.');
      return;
    }

    if (isRegister) {
      if (password.length < 6) {
        setLocalError('Password must be at least 6 characters.');
        return;
      }
      if (password !== confirmPassword) {
        setLocalError('Passwords do not match.');
        return;
      }
    }

    setSubmitting(true);
    try {
      if (isRegister) {
        const result = await register(email, password);
        if (result?.user && !result?.session) {
          setSuccessMessage(
            'Registration successful! Please check your email to confirm your account, then log in.'
          );
          setIsRegister(false);
        } else {
          navigate(from, { replace: true });
        }
      } else {
        await login(email, password);
        navigate(from, { replace: true });
      }
    } catch (err) {
      setLocalError(err.message || 'Authentication failed. Please check your credentials.');
    } finally {
      setSubmitting(false);
    }
  };

  const handleDemoLogin = () => {
    loginDemoUser();
    navigate(from, { replace: true });
  };

  return (
    <div className="min-h-screen flex flex-col justify-between bg-slate-950 text-slate-100 relative overflow-hidden">
      {/* Background ambient lighting */}
      <div className="absolute top-0 left-1/2 -translate-x-1/2 w-[800px] h-[400px] bg-gradient-to-b from-indigo-600/15 via-violet-600/10 to-transparent blur-3xl pointer-events-none -z-0" />
      <div className="absolute bottom-0 right-10 w-[500px] h-[300px] bg-blue-600/10 blur-3xl pointer-events-none -z-0" />

      {/* Top Navbar */}
      <header className="px-6 py-5 flex items-center justify-between relative z-10 max-w-6xl w-full mx-auto">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-indigo-600 via-indigo-500 to-violet-500 flex items-center justify-center text-white shadow-lg shadow-indigo-500/20">
            <SearchCode className="w-5 h-5" />
          </div>
          <div>
            <span className="font-bold text-lg text-white tracking-tight">InfoScope</span>
            <span className="ml-1 text-xs font-semibold px-1.5 py-0.5 rounded bg-indigo-500/20 text-indigo-400 border border-indigo-500/30">AI</span>
          </div>
        </div>

        <button
          onClick={toggleTheme}
          className="p-2 rounded-xl text-slate-400 hover:text-white hover:bg-slate-900 border border-slate-800 transition-colors"
          title="Toggle Theme"
        >
          {isDark ? <Sun className="w-4 h-4 text-amber-400" /> : <Moon className="w-4 h-4 text-indigo-400" />}
        </button>
      </header>

      {/* Central Auth Card */}
      <main className="flex-1 flex items-center justify-center p-4 sm:p-6 relative z-10">
        <div className="w-full max-w-md">
          {/* Card Container */}
          <div className="rounded-3xl bg-slate-900/90 border border-slate-800/80 p-6 sm:p-8 shadow-2xl backdrop-blur-xl">
            {/* Header */}
            <div className="text-center mb-6">
              <h1 className="text-2xl font-bold text-white tracking-tight">
                {isRegister ? 'Create an Account' : 'Welcome to InfoScope AI'}
              </h1>
              <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">
                {isRegister
                  ? 'Sign up to analyze information gaps, conflicting claims, and source coverage.'
                  : 'Log in with Supabase Authentication to access your research dashboard.'}
              </p>
            </div>

            {/* Supabase Notice banner if credentials are not yet configured */}
            {!isConfigured && (
              <div className="mb-5 p-3.5 rounded-2xl bg-indigo-950/40 border border-indigo-800/50 text-indigo-200 text-xs flex gap-3">
                <Info className="w-5 h-5 text-indigo-400 shrink-0 mt-0.5" />
                <div className="space-y-1">
                  <p className="font-semibold text-indigo-300">Live Supabase Keys Pending</p>
                  <p className="text-[11px] text-slate-300 leading-normal">
                    Add <code className="px-1 py-0.5 bg-slate-800 rounded text-indigo-300">VITE_SUPABASE_URL</code> and{' '}
                    <code className="px-1 py-0.5 bg-slate-800 rounded text-indigo-300">VITE_SUPABASE_ANON_KEY</code> to{' '}
                    <code className="px-1 py-0.5 bg-slate-800 rounded text-slate-300">frontend/.env</code> for live registration.
                  </p>
                </div>
              </div>
            )}

            {/* Error / Success Alerts */}
            {localError && (
              <div className="mb-4 p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-start gap-2.5">
                <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                <span>{localError}</span>
              </div>
            )}

            {successMessage && (
              <div className="mb-4 p-3 rounded-xl bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs flex items-start gap-2.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                <span>{successMessage}</span>
              </div>
            )}

            {/* Form */}
            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Email Address
                </label>
                <div className="relative">
                  <Mail className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="email"
                    id="auth-email-input"
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    placeholder="researcher@organization.com"
                    required
                    className="w-full bg-slate-950/70 border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1.5">
                  Password
                </label>
                <div className="relative">
                  <Lock className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                  <input
                    type="password"
                    id="auth-password-input"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="••••••••••••"
                    required
                    className="w-full bg-slate-950/70 border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
                  />
                </div>
              </div>

              {isRegister && (
                <div>
                  <label className="block text-xs font-medium text-slate-300 mb-1.5">
                    Confirm Password
                  </label>
                  <div className="relative">
                    <KeyRound className="w-4 h-4 text-slate-500 absolute left-3.5 top-1/2 -translate-y-1/2" />
                    <input
                      type="password"
                      id="auth-confirm-password-input"
                      value={confirmPassword}
                      onChange={(e) => setConfirmPassword(e.target.value)}
                      placeholder="••••••••••••"
                      required
                      className="w-full bg-slate-950/70 border border-slate-800 rounded-xl pl-10 pr-4 py-2.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
                    />
                  </div>
                </div>
              )}

              {/* Submit Button */}
              <button
                type="submit"
                id="auth-submit-button"
                disabled={submitting}
                className="w-full mt-2 py-2.5 px-4 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-medium text-sm flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
              >
                {submitting ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    <span>Processing...</span>
                  </>
                ) : (
                  <>
                    <span>{isRegister ? 'Register with Supabase' : 'Sign In'}</span>
                    <ArrowRight className="w-4 h-4" />
                  </>
                )}
              </button>
            </form>

            {/* Tab switch */}
            <div className="mt-5 text-center">
              <button
                type="button"
                onClick={() => {
                  setIsRegister(!isRegister);
                  setLocalError('');
                  setSuccessMessage('');
                }}
                className="text-xs text-slate-400 hover:text-indigo-400 transition-colors"
              >
                {isRegister
                  ? 'Already have an account? Sign In'
                  : "Don't have an account? Register here"}
              </button>
            </div>

            {/* Instant Demo Access Button */}
            <div className="mt-6 pt-5 border-t border-slate-800/80">
              <button
                type="button"
                id="auth-demo-login-button"
                onClick={handleDemoLogin}
                className="w-full py-2.5 px-4 rounded-xl bg-slate-800/60 hover:bg-slate-800 border border-slate-700/80 text-slate-300 hover:text-white text-xs font-medium flex items-center justify-center gap-2 transition-all cursor-pointer"
              >
                <Sparkles className="w-4 h-4 text-indigo-400" />
                <span>Instant Demo Preview (Explore Dashboard)</span>
              </button>
            </div>
          </div>
        </div>
      </main>

      {/* Footer */}
      <footer className="py-4 text-center text-xs text-slate-400 relative z-10 border-t border-slate-900">
        InfoScope AI — Initial Production Foundation &copy; {new Date().getFullYear()}
      </footer>
    </div>
  );
};
