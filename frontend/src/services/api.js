import axios from 'axios';
import { supabase } from '../lib/supabaseClient';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to attach Supabase JWT Bearer token if session exists
apiClient.interceptors.request.use(
  async (config) => {
    try {
      const { data: { session } } = await supabase.auth.getSession();
      if (session?.access_token) {
        config.headers.Authorization = `Bearer ${session.access_token}`;
      }
    } catch {
      // Continue without token if session check fails or in demo mode
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Health check service
export const checkBackendHealth = async () => {
  const response = await apiClient.get('/api/v1/health');
  return response.data;
};

// Root API info service
export const getApiRoot = async () => {
  const response = await apiClient.get('/');
  return response.data;
};
