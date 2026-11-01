import axios from 'axios';
import { supabase } from '../lib/supabaseClient';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'http://localhost:8000';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
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

// Research Session services
export const listResearchSessions = async ({ limit = 50, offset = 0, status } = {}) => {
  const params = { limit, offset };
  if (status) params.status = status;
  const response = await apiClient.get('/api/v1/research/sessions', { params });
  return response.data;
};

export const getResearchSession = async (sessionId) => {
  const response = await apiClient.get(`/api/v1/research/sessions/${sessionId}`);
  return response.data;
};

export const getResearchSessionStatus = async (sessionId) => {
  const response = await apiClient.get(`/api/v1/research/sessions/${sessionId}/status`);
  return response.data;
};

export const getResearchSessionSources = async (sessionId, { limit = 50, offset = 0 } = {}) => {
  const response = await apiClient.get(`/api/v1/research/sessions/${sessionId}/sources`, {
    params: { limit, offset },
  });
  return response.data;
};

export const updateResearchSession = async (sessionId, data) => {
  const response = await apiClient.patch(`/api/v1/research/sessions/${sessionId}`, data);
  return response.data;
};

// Expected Fields & Coverage services (Stage 3, Phase 3, Step 3)
export const listExpectedFields = async (sessionId, { status } = {}) => {
  const params = {};
  if (status) params.status = status;
  const response = await apiClient.get(`/api/v1/research/sessions/${sessionId}/expected-fields`, { params });
  return response.data;
};

export const createExpectedField = async (sessionId, fieldData) => {
  const response = await apiClient.post(`/api/v1/research/sessions/${sessionId}/expected-fields`, fieldData);
  return response.data;
};

export const updateExpectedField = async (sessionId, fieldId, fieldData) => {
  const response = await apiClient.patch(`/api/v1/research/sessions/${sessionId}/expected-fields/${fieldId}`, fieldData);
  return response.data;
};

export const deleteExpectedField = async (sessionId, fieldId) => {
  const response = await apiClient.delete(`/api/v1/research/sessions/${sessionId}/expected-fields/${fieldId}`);
  return response.data;
};

export const getResearchSessionCoverage = async (sessionId) => {
  const response = await apiClient.get(`/api/v1/research/sessions/${sessionId}/coverage`);
  return response.data;
};
