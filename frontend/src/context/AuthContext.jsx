import React, { createContext, useContext, useEffect, useState } from 'react';
import { supabase, isSupabaseConfigured } from '../lib/supabaseClient';

const AuthContext = createContext();

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isDemoUser, setIsDemoUser] = useState(false);

  useEffect(() => {
    let mounted = true;

    // Check for demo user in local session storage
    const storedDemo = sessionStorage.getItem('infoscope_demo_user');
    if (storedDemo) {
      try {
        const parsed = JSON.parse(storedDemo);
        setUser(parsed);
        setIsDemoUser(true);
        setLoading(false);
        return;
      } catch {
        sessionStorage.removeItem('infoscope_demo_user');
      }
    }

    if (!isSupabaseConfigured) {
      setLoading(false);
      return;
    }

    // Initialize Supabase session
    const initializeAuth = async () => {
      try {
        const { data: { session: initialSession }, error: sessionError } = await supabase.auth.getSession();
        if (sessionError) throw sessionError;
        if (mounted) {
          setSession(initialSession);
          setUser(initialSession?.user ?? null);
        }
      } catch (err) {
        console.error('Error fetching Supabase session:', err);
      } finally {
        if (mounted) setLoading(false);
      }
    };

    initializeAuth();

    // Listen to Supabase auth state changes
    const { data: { subscription } } = supabase.auth.onAuthStateChange(
      (_event, currentSession) => {
        if (mounted) {
          setSession(currentSession);
          setUser(currentSession?.user ?? null);
          setIsDemoUser(false);
          setLoading(false);
        }
      }
    );

    return () => {
      mounted = false;
      subscription?.unsubscribe();
    };
  }, []);

  // Email / Password Login
  const login = async (email, password) => {
    setError(null);
    if (!isSupabaseConfigured) {
      throw new Error(
        'Supabase keys are not configured yet. Please update VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env, or use Demo Mode to preview.'
      );
    }

    const { data, error: authError } = await supabase.auth.signInWithPassword({
      email,
      password,
    });

    if (authError) {
      setError(authError.message);
      throw authError;
    }

    setUser(data.user);
    setSession(data.session);
    setIsDemoUser(false);
    return data;
  };

  // Email / Password Registration
  const register = async (email, password) => {
    setError(null);
    if (!isSupabaseConfigured) {
      throw new Error(
        'Supabase keys are not configured yet. Please update VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY in frontend/.env to enable live user registration.'
      );
    }

    const { data, error: authError } = await supabase.auth.signUp({
      email,
      password,
    });

    if (authError) {
      setError(authError.message);
      throw authError;
    }

    // Some Supabase configurations require email confirmation
    if (data.session) {
      setUser(data.user);
      setSession(data.session);
    }
    return data;
  };

  // Logout
  const logout = async () => {
    setError(null);
    if (isDemoUser) {
      sessionStorage.removeItem('infoscope_demo_user');
      setUser(null);
      setIsDemoUser(false);
      return;
    }

    if (isSupabaseConfigured) {
      await supabase.auth.signOut();
    }
    setUser(null);
    setSession(null);
  };

  // Demo user login for immediate inspection when keys are placeholders
  const loginDemoUser = (email = 'researcher@infoscope.ai') => {
    const demo = {
      id: 'demo-user-8842-infoscope',
      email,
      user_metadata: { full_name: 'Lead AI Researcher' },
      role: 'authenticated',
      isDemo: true,
    };
    sessionStorage.setItem('infoscope_demo_user', JSON.stringify(demo));
    setUser(demo);
    setIsDemoUser(true);
    setError(null);
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        session,
        loading,
        error,
        setError,
        login,
        register,
        logout,
        loginDemoUser,
        isConfigured: isSupabaseConfigured,
        isDemoUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};
