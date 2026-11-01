import assert from 'node:assert';
import test from 'node:test';
import { classifySearchError, getPartialSuccessInfo } from './searchErrors.js';

test('Scenario 1: Tavily provider times out', () => {
  const providerStatuses = {
    tavily: { success: false, result_count: 0, latency_seconds: 15.0, error_message: 'Tavily search request timed out after 15.0s' }
  };

  const diag = classifySearchError(new Error('Search failed'), providerStatuses);
  assert.strictEqual(diag.category, 'PROVIDER_TIMEOUT');
  assert.strictEqual(diag.responsibleProvider, 'tavily');
  assert.match(diag.title, /Tavily Search Timed Out/i);
});

test('Scenario 2: Tavily authentication failed (invalid API key)', () => {
  const providerStatuses = {
    tavily: { success: false, result_count: 0, latency_seconds: 0.4, error_message: 'Tavily authentication failed: invalid API key (401).' }
  };

  const diag = classifySearchError(new Error('Auth failed'), providerStatuses);
  assert.strictEqual(diag.category, 'AUTH_ERROR');
  assert.strictEqual(diag.responsibleProvider, 'tavily');
  assert.match(diag.title, /Tavily Authentication Failed/i);
  assert.match(diag.suggestedAction, /TAVILY_API_KEY/i);
});

test('Scenario 3: Tavily general search failure', () => {
  const providerStatuses = {
    tavily: { success: false, result_count: 0, latency_seconds: 1.2, error_message: 'Tavily API responded with HTTP 500' }
  };

  const diag = classifySearchError(new Error('Internal server error'), providerStatuses);
  assert.strictEqual(diag.category, 'SEARCH_FAILED');
  assert.strictEqual(diag.responsibleProvider, 'tavily');
  assert.match(diag.title, /Tavily Search Failed/i);
});

test('Scenario 4: Client Axios timeout (timeout of 10000ms exceeded)', () => {
  const axiosError = new Error('timeout of 10000ms exceeded');
  axiosError.code = 'ECONNABORTED';

  const diag = classifySearchError(axiosError);
  assert.strictEqual(diag.category, 'CLIENT_TIMEOUT');
  assert.strictEqual(diag.responsibleProvider, 'client');
  assert.match(diag.title, /Timed Out/i);
  assert.match(diag.suggestedAction, /45s/i);
});

test('Scenario 5: Network connection error', () => {
  const netError = new Error('Network Error');
  netError.code = 'ERR_NETWORK';

  const diag = classifySearchError(netError);
  assert.strictEqual(diag.category, 'NETWORK_ERROR');
  assert.match(diag.title, /Unreachable/i);
});

test('Scenario 6: Partial success helper handles provider and custom sources', () => {
  const providerStatuses = {
    tavily: { success: true, result_count: 5, latency_seconds: 1.8 },
    custom_url: { success: false, result_count: 0, error_message: 'Failed to fetch custom URL' }
  };

  const partialInfo = getPartialSuccessInfo(providerStatuses);
  assert.strictEqual(partialInfo?.isPartial, true);
  assert.strictEqual(partialInfo?.succeededCount, 1);
  assert.strictEqual(partialInfo?.failedDescriptions[0].provider, 'custom_url');
});
