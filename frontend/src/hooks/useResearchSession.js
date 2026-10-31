import { useState, useCallback } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '../services/api';

/**
 * Custom hook to manage research session submissions and caching.
 */
export const useResearchSession = () => {
  const [activeSession, setActiveSession] = useState(null);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: async ({ query, sourceSelection, customUrls }) => {
      const response = await apiClient.post('/api/v1/research/sessions', {
        research_query: query,
        source_selection: sourceSelection,
        custom_urls: customUrls,
      });
      return response.data;
    },
    onSuccess: (data) => {
      setActiveSession(data?.data);
      queryClient.invalidateQueries({ queryKey: ['researchSessions'] });
    },
  });

  const triggerAnalysis = useCallback(
    (query, sourceSelection = 'both', customUrls = []) => {
      return mutation.mutateAsync({ query, sourceSelection, customUrls });
    },
    [mutation]
  );

  return {
    triggerAnalysis,
    isLoading: mutation.isPending,
    error: mutation.error,
    activeSession,
    reset: mutation.reset,
  };
};
