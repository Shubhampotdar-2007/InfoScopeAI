/**
 * Diagnostics utility to classify InfoScope AI search execution errors.
 * Distinguishes between:
 * - Tavily provider timeouts
 * - Tavily authentication / API key errors
 * - Client request timeouts (Axios ECONNABORTED)
 * - Network / backend connectivity errors
 * - HTTP / API configuration errors
 */

export const classifySearchError = (error, providerStatuses = null, searchError = null) => {
  // 1. Check backend-reported provider statuses if available
  if (providerStatuses && typeof providerStatuses === 'object') {
    const entries = Object.entries(providerStatuses);
    const failed = entries.filter(([_, s]) => s && !s.success);
    const succeeded = entries.filter(([_, s]) => s && s.success);

    // If all queried providers failed
    if (entries.length > 0 && failed.length === entries.length && succeeded.length === 0) {
      const isTimeout = (msg) => {
        const lower = String(msg || '').toLowerCase();
        return lower.includes('timed out') || lower.includes('timeout');
      };

      const isAuth = (msg) => {
        const lower = String(msg || '').toLowerCase();
        return (
          lower.includes('api key') ||
          lower.includes('authentication') ||
          lower.includes('unauthorized') ||
          lower.includes('401')
        );
      };

      const timeoutProviders = failed.filter(([_, s]) => isTimeout(s?.error_message));
      const authProviders = failed.filter(([_, s]) => isAuth(s?.error_message));

      // Case A: Tavily / provider timed out
      if (timeoutProviders.length > 0) {
        return {
          category: 'PROVIDER_TIMEOUT',
          responsibleProvider: 'tavily',
          title: 'Tavily Search Timed Out',
          message: 'Tavily exceeded the configured provider timeout limits during web retrieval.',
          details: failed.map(([p, s]) => `${p}: ${s?.error_message || 'Timeout'}`).join(' | '),
          suggestedAction:
            'The external search engine took too long to complete. Try a more specific query or check network latency.',
        };
      }

      // Case B: Auth / API Key failure
      if (authProviders.length > 0) {
        return {
          category: 'AUTH_ERROR',
          responsibleProvider: 'tavily',
          title: 'Tavily Authentication Failed',
          message: 'Authentication failed for Tavily. Please verify your TAVILY_API_KEY in backend/.env.',
          details: failed.map(([p, s]) => `${p}: ${s?.error_message}`).join(' | '),
          suggestedAction: 'Verify TAVILY_API_KEY in backend/.env.',
        };
      }

      // Case C: General failure
      return {
        category: 'SEARCH_FAILED',
        responsibleProvider: 'tavily',
        title: 'Tavily Search Failed',
        message: searchError || 'Tavily search provider failed to return results.',
        details: failed.map(([p, s]) => `${p}: ${s?.error_message}`).join(' | '),
        suggestedAction: 'Review the Tavily error message or check your backend connection.',
      };
    }
  }

  // 2. Check Axios / Network level errors
  const rawMsg = error?.response?.data?.message || error?.message || String(error || '');
  const lowerMsg = rawMsg.toLowerCase();
  const statusCode = error?.response?.status;

  // Axios Client Timeout (e.g. "timeout of 10000ms exceeded" or code ECONNABORTED)
  if (error?.code === 'ECONNABORTED' || lowerMsg.includes('timeout of') || lowerMsg.includes('client timeout')) {
    return {
      category: 'CLIENT_TIMEOUT',
      responsibleProvider: 'client',
      title: 'Search Request Timed Out (Client)',
      message: 'The search request exceeded the client timeout limit before the backend finished.',
      details: rawMsg,
      suggestedAction: 'Tavily search and synthesis take time. The client timeout allows up to 45s.',
    };
  }

  // Network / Connection Error
  if (
    error?.code === 'ERR_NETWORK' ||
    lowerMsg.includes('network error') ||
    lowerMsg.includes('failed to fetch') ||
    (!error?.response && error?.request)
  ) {
    return {
      category: 'NETWORK_ERROR',
      responsibleProvider: null,
      title: 'Network / Backend Unreachable',
      message: 'Unable to connect to the InfoScope AI backend server.',
      details: rawMsg,
      suggestedAction: 'Ensure the backend server is running at http://localhost:8000 and accessible.',
    };
  }

  // Authentication error (401 Unauthorized from backend or Supabase)
  if (statusCode === 401 || lowerMsg.includes('authentication failed') || lowerMsg.includes('jwt')) {
    return {
      category: 'AUTH_ERROR',
      responsibleProvider: null,
      title: 'Authentication Required',
      message: 'User authentication failed or session expired.',
      details: rawMsg,
      suggestedAction: 'Please log in again or check your authentication session.',
    };
  }

  // HTTP or Configuration Error
  return {
    category: 'CONFIG_OR_HTTP_ERROR',
    responsibleProvider: null,
    title: 'Search Execution Error',
    message: rawMsg || 'An unexpected error occurred during search execution.',
    details: rawMsg,
    suggestedAction: 'Check the backend logs for detailed stack trace and response data.',
  };
};

/**
 * Checks if a search execution resulted in partial success.
 */
export const getPartialSuccessInfo = (providerStatuses) => {
  if (!providerStatuses || typeof providerStatuses !== 'object') {
    return null;
  }

  const entries = Object.entries(providerStatuses);
  const succeeded = entries.filter(([_, s]) => s && s.success);
  const failed = entries.filter(([_, s]) => s && !s.success);

  if (succeeded.length > 0 && failed.length > 0) {
    const failedDescriptions = failed.map(([p, s]) => {
      const name = p === 'tavily' ? 'Tavily' : p;
      const msg = s?.error_message || 'Failed';
      const isTimeout = msg.toLowerCase().includes('timed out') || msg.toLowerCase().includes('timeout');
      return {
        provider: p,
        name,
        isTimeout,
        message: msg,
      };
    });

    return {
      isPartial: true,
      succeededCount: succeeded.length,
      failedDescriptions,
    };
  }

  return null;
};
