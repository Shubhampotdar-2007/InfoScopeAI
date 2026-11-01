import React, { useState, useEffect } from 'react';
import { useSearchParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Card } from '../components/common/Card';
import { Badge } from '../components/common/Badge';
import { useAuth } from '../context/AuthContext';
import {
  Globe,
  Link2,
  Layers,
  Sparkles,
  Search,
  AlertTriangle,
  FileQuestion,
  CheckCircle2,
  Plus,
  Trash2,
  ExternalLink,
  ChevronRight,
  Info,
  BarChart3,
  ListChecks,
  ArrowLeft,
  Edit3,
  Save,
  X,
  RefreshCw,
  Clock,
  Cpu,
  BookOpen,
  HelpCircle,
  Loader2,
  Check,
} from 'lucide-react';
import { useResearchSession } from '../hooks/useResearchSession';
import { classifySearchError } from '../utils/searchErrors';
import {
  listResearchSessions,
  getResearchSession,
  updateResearchSession,
  listExpectedFields,
  createExpectedField,
  updateExpectedField,
  deleteExpectedField,
  getResearchSessionCoverage,
} from '../services/api';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
} from 'recharts';

export const DashboardPage = ({ defaultView }) => {
  const { user, isDemoUser } = useAuth();
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();

  // Active Session Navigation via URL Query Param
  const activeSessionId = searchParams.get('session');
  const activeTab = searchParams.get('tab') || 'sources';

  // Research input form state
  const [researchQuery, setResearchQuery] = useState('');
  const [sourceStrategy, setSourceStrategy] = useState('both'); // 'web', 'urls', 'both'
  const [customUrls, setCustomUrls] = useState(['']);
  const [submissionError, setSubmissionError] = useState(null);
  const [diagnosticInfo, setDiagnosticInfo] = useState(null);

  // Session Title Editing State
  const [isEditingTitle, setIsEditingTitle] = useState(false);
  const [titleDraft, setTitleDraft] = useState('');

  // Add Expected Field Modal State
  const [isAddFieldOpen, setIsAddFieldOpen] = useState(false);
  const [fieldName, setFieldName] = useState('');
  const [fieldCategory, setFieldCategory] = useState('General');
  const [fieldDescription, setFieldDescription] = useState('');
  const [fieldWeight, setFieldWeight] = useState(1.0);
  const [fieldRequired, setFieldRequired] = useState(true);
  const [fieldActionError, setFieldActionError] = useState(null);

  // Edit Expected Field State
  const [editingFieldId, setEditingFieldId] = useState(null);
  const [editFieldName, setEditFieldName] = useState('');
  const [editFieldDescription, setEditFieldDescription] = useState('');
  const [editFieldWeight, setEditFieldWeight] = useState(1.0);

  // Research Hook
  const { triggerAnalysis, isLoading: isHookLoading } = useResearchSession();
  const [localAnalyzing, setLocalAnalyzing] = useState(false);
  const isAnalyzing = isHookLoading || localAnalyzing;

  // Query: User's Historical Sessions (Supabase RLS Protected)
  const {
    data: sessionsData,
    isLoading: isSessionsLoading,
    isError: isSessionsError,
    refetch: refetchSessions,
  } = useQuery({
    queryKey: ['researchSessions'],
    queryFn: () => listResearchSessions({ limit: 50 }),
    staleTime: 15000,
  });

  const sessionList = sessionsData?.data || [];

  // Query: Active Session Details & Sources
  const {
    data: activeSessionResponse,
    isLoading: isActiveSessionLoading,
    isError: isActiveSessionError,
    refetch: refetchActiveSession,
  } = useQuery({
    queryKey: ['researchSession', activeSessionId],
    queryFn: () => getResearchSession(activeSessionId),
    enabled: Boolean(activeSessionId),
    staleTime: 10000,
  });

  const activeSession = activeSessionResponse?.data;
  const activeSources = activeSession?.sources || [];

  // Query: Expected Fields for Active Session
  const {
    data: expectedFieldsResponse,
    isLoading: isFieldsLoading,
    refetch: refetchExpectedFields,
  } = useQuery({
    queryKey: ['expectedFields', activeSessionId],
    queryFn: () => listExpectedFields(activeSessionId),
    enabled: Boolean(activeSessionId),
    staleTime: 10000,
  });

  const expectedFields = expectedFieldsResponse?.data || [];

  // Query: Real Coverage Metrics for Active Session
  const {
    data: coverageResponse,
    isLoading: isCoverageLoading,
    refetch: refetchCoverage,
  } = useQuery({
    queryKey: ['sessionCoverage', activeSessionId],
    queryFn: () => getResearchSessionCoverage(activeSessionId),
    enabled: Boolean(activeSessionId),
    staleTime: 10000,
  });

  const coverageData = coverageResponse?.data;

  // Initialize Title Draft when activeSession changes
  useEffect(() => {
    if (activeSession?.title) {
      setTitleDraft(activeSession.title);
    }
  }, [activeSession?.title]);

  // Handle defaultView props
  useEffect(() => {
    if (defaultView === 'new' && activeSessionId) {
      setSearchParams({});
    }
  }, [defaultView]);

  // Navigation Helpers
  const selectSession = (sessionId) => {
    setSearchParams({ session: sessionId, tab: 'sources' });
  };

  const clearActiveSession = () => {
    setSearchParams({});
    setSubmissionError(null);
    setDiagnosticInfo(null);
  };

  const switchTab = (tabName) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev);
      next.set('tab', tabName);
      return next;
    });
  };

  // URL input management
  const handleAddUrl = () => {
    if (customUrls.length < 5) {
      setCustomUrls([...customUrls, '']);
    }
  };

  const handleUpdateUrl = (index, value) => {
    const updated = [...customUrls];
    updated[index] = value;
    setCustomUrls(updated);
  };

  const handleRemoveUrl = (index) => {
    if (customUrls.length > 1) {
      setCustomUrls(customUrls.filter((_, i) => i !== index));
    } else {
      setCustomUrls(['']);
    }
  };

  // Submit trigger: New Research Investigation
  const handleStartAnalysis = async (e) => {
    e.preventDefault();
    const queryClean = researchQuery.trim();
    if (!queryClean) return;

    setLocalAnalyzing(true);
    setSubmissionError(null);
    setDiagnosticInfo(null);
    const validUrls = customUrls.filter((u) => u.trim() !== '');

    try {
      const response = await triggerAnalysis(queryClean, sourceStrategy, 'tavily', validUrls);
      const resData = response?.data || {};
      const newSessionId = resData.session_id;

      // Invalidate sessions list query
      queryClient.invalidateQueries({ queryKey: ['researchSessions'] });

      if (newSessionId) {
        setSearchParams({ session: newSessionId, tab: 'sources' });
      }

      setResearchQuery('');
      setCustomUrls(['']);
    } catch (err) {
      const providerStatuses = err.response?.data?.data?.provider_statuses || null;
      const searchError = err.response?.data?.data?.search_error || err.response?.data?.message || err.message;
      const diag = classifySearchError(err, providerStatuses, searchError);
      setDiagnosticInfo(diag);
      setSubmissionError(diag.message || 'Failed to initialize research session.');
    } finally {
      setLocalAnalyzing(false);
    }
  };

  // Mutation: Update Session Title
  const handleSaveTitle = async () => {
    const cleanTitle = titleDraft.trim();
    if (!cleanTitle || cleanTitle === activeSession?.title) {
      setIsEditingTitle(false);
      return;
    }

    try {
      await updateResearchSession(activeSessionId, { title: cleanTitle });
      queryClient.invalidateQueries({ queryKey: ['researchSession', activeSessionId] });
      queryClient.invalidateQueries({ queryKey: ['researchSessions'] });
      setIsEditingTitle(false);
    } catch (err) {
      console.error('Failed to update session title:', err);
    }
  };

  // Mutation: Create Expected Field
  const handleCreateExpectedField = async (e) => {
    e.preventDefault();
    const cleanName = fieldName.trim();
    if (!cleanName) return;

    setFieldActionError(null);
    try {
      await createExpectedField(activeSessionId, {
        field_name: cleanName,
        field_category: fieldCategory.trim() || 'General',
        description: fieldDescription.trim() || null,
        weight: parseFloat(fieldWeight) || 1.0,
        is_required: fieldRequired,
        status: 'missing',
      });

      queryClient.invalidateQueries({ queryKey: ['expectedFields', activeSessionId] });
      queryClient.invalidateQueries({ queryKey: ['sessionCoverage', activeSessionId] });

      setFieldName('');
      setFieldDescription('');
      setFieldWeight(1.0);
      setIsAddFieldOpen(false);
    } catch (err) {
      const msg = err.response?.data?.message || err.message || 'Failed to create expected field.';
      setFieldActionError(msg);
    }
  };

  // Mutation: Batch Load Starter Evaluation Framework
  const handleLoadStarterFramework = async () => {
    setFieldActionError(null);
    const starterFields = [
      {
        field_name: 'Core Architecture & Technical Stack',
        field_category: 'Architecture',
        weight: 1.5,
        description: 'Underlying runtime, database design, API protocols, and scalability architecture.',
        is_required: true,
      },
      {
        field_name: 'Pricing Structure & Quotas',
        field_category: 'Pricing',
        weight: 1.0,
        description: 'Pricing tiers, free allowance, overage charges, and enterprise license costs.',
        is_required: true,
      },
      {
        field_name: 'Security, Compliance & RBAC',
        field_category: 'Security',
        weight: 1.5,
        description: 'Authentication mechanisms, data encryption, RBAC granular permissions, and compliance certifications.',
        is_required: true,
      },
      {
        field_name: 'Performance & Latency Benchmarks',
        field_category: 'Performance',
        weight: 1.0,
        description: 'Throughput metrics, cold-start latencies, burst limits, and regional availability.',
        is_required: false,
      },
    ];

    try {
      for (const f of starterFields) {
        await createExpectedField(activeSessionId, {
          ...f,
          status: 'missing',
        });
      }
      queryClient.invalidateQueries({ queryKey: ['expectedFields', activeSessionId] });
      queryClient.invalidateQueries({ queryKey: ['sessionCoverage', activeSessionId] });
    } catch (err) {
      const msg = err.response?.data?.message || err.message || 'Failed to add starter fields.';
      setFieldActionError(msg);
    }
  };

  // Mutation: Update Expected Field
  const handleStartEditField = (field) => {
    setEditingFieldId(field.id);
    setEditFieldName(field.field_name);
    setEditFieldDescription(field.description || '');
    setEditFieldWeight(field.weight || 1.0);
    setFieldActionError(null);
  };

  const handleSaveEditField = async (fieldId) => {
    const cleanName = editFieldName.trim();
    if (!cleanName) return;

    setFieldActionError(null);
    try {
      await updateExpectedField(activeSessionId, fieldId, {
        field_name: cleanName,
        description: editFieldDescription.trim() || null,
        weight: parseFloat(editFieldWeight) || 1.0,
      });

      queryClient.invalidateQueries({ queryKey: ['expectedFields', activeSessionId] });
      queryClient.invalidateQueries({ queryKey: ['sessionCoverage', activeSessionId] });
      setEditingFieldId(null);
    } catch (err) {
      const msg = err.response?.data?.message || err.message || 'Failed to update field.';
      setFieldActionError(msg);
    }
  };

  // Mutation: Delete Expected Field
  const handleDeleteField = async (fieldId) => {
    setFieldActionError(null);
    try {
      await deleteExpectedField(activeSessionId, fieldId);
      queryClient.invalidateQueries({ queryKey: ['expectedFields', activeSessionId] });
      queryClient.invalidateQueries({ queryKey: ['sessionCoverage', activeSessionId] });
    } catch (err) {
      const msg = err.response?.data?.message || err.message || 'Failed to delete field.';
      setFieldActionError(msg);
    }
  };

  // Prepare Real Chart Data for Coverage Tab
  const categoryMap = {};
  expectedFields.forEach((f) => {
    const cat = f.field_category || 'General';
    if (!categoryMap[cat]) {
      categoryMap[cat] = { category: cat, totalWeight: 0, coveredWeight: 0 };
    }
    const w = parseFloat(f.weight) || 1.0;
    categoryMap[cat].totalWeight += w;
    if (f.status === 'covered') {
      categoryMap[cat].coveredWeight += w;
    } else if (f.status === 'partially_covered') {
      categoryMap[cat].coveredWeight += w * 0.5;
    }
  });

  const chartData = Object.values(categoryMap).map((c) => ({
    category: c.category,
    coverage: c.totalWeight > 0 ? Math.round((c.coveredWeight / c.totalWeight) * 100) : 0,
    fill: '#6366f1',
  }));

  // ============================================================================
  // RENDER: ACTIVE RESEARCH SESSION VIEW
  // ============================================================================
  if (activeSessionId) {
    return (
      <div className="max-w-7xl mx-auto space-y-6">
        {/* Top Back Navigation & Session Meta Banner */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-start sm:items-center gap-3">
            <button
              onClick={clearActiveSession}
              className="p-2 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 transition-colors cursor-pointer shrink-0 mt-0.5 sm:mt-0"
              title="Return to New Search and Session History"
            >
              <ArrowLeft className="w-5 h-5" />
            </button>

            <div className="min-w-0">
              {isEditingTitle ? (
                <div className="flex items-center gap-2">
                  <input
                    type="text"
                    value={titleDraft}
                    onChange={(e) => setTitleDraft(e.target.value)}
                    className="bg-slate-50 dark:bg-slate-950 border border-indigo-500 rounded-lg px-2.5 py-1 text-sm font-bold text-slate-900 dark:text-white focus:outline-none"
                    autoFocus
                  />
                  <button
                    onClick={handleSaveTitle}
                    className="p-1.5 rounded-lg text-emerald-500 hover:bg-emerald-500/10"
                    title="Save Title"
                  >
                    <Save className="w-4 h-4" />
                  </button>
                  <button
                    onClick={() => {
                      setIsEditingTitle(false);
                      setTitleDraft(activeSession?.title || '');
                    }}
                    className="p-1.5 rounded-lg text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                    title="Cancel"
                  >
                    <X className="w-4 h-4" />
                  </button>
                </div>
              ) : (
                <div className="flex items-center gap-2">
                  <h1 className="text-xl sm:text-2xl font-bold tracking-tight text-slate-900 dark:text-white truncate">
                    {activeSession?.title || 'Research Investigation'}
                  </h1>
                  <button
                    onClick={() => setIsEditingTitle(true)}
                    className="p-1 rounded text-slate-400 hover:text-indigo-500 transition-colors"
                    title="Edit Session Title"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 flex items-center gap-2 truncate">
                <span className="font-medium text-slate-700 dark:text-slate-300">Query:</span>
                <span className="italic">"{activeSession?.research_query}"</span>
              </p>
            </div>
          </div>

          {/* Session Diagnostics and Lifecycle Pill */}
          <div className="flex flex-wrap items-center gap-2.5 self-start md:self-auto">
            <Badge
              variant={
                activeSession?.status === 'completed'
                  ? 'success'
                  : activeSession?.status === 'failed'
                  ? 'danger'
                  : 'primary'
              }
              size="sm"
            >
              Status: {activeSession?.status || 'Active'}
            </Badge>

            <Badge variant="info" size="sm">
              Provider: Tavily Search
            </Badge>

            {coverageData && (
              <Badge variant="neutral" size="sm">
                Score: {coverageData.coverage_score}%
              </Badge>
            )}

            <button
              onClick={() => {
                refetchActiveSession();
                refetchExpectedFields();
                refetchCoverage();
              }}
              className="p-1.5 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors cursor-pointer"
              title="Refresh Session Data"
            >
              <RefreshCw className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Tab Selection Navigation */}
        <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 pb-1 overflow-x-auto">
          <button
            onClick={() => switchTab('sources')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              activeTab === 'sources'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800'
            }`}
          >
            <Globe className="w-4 h-4" />
            <span>Retrieved Sources</span>
            <span className="px-1.5 py-0.2 rounded-md bg-white/20 text-[10px]">
              {activeSources.length}
            </span>
          </button>

          <button
            onClick={() => switchTab('fields')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              activeTab === 'fields'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800'
            }`}
          >
            <ListChecks className="w-4 h-4" />
            <span>Expected Dimensions</span>
            <span className="px-1.5 py-0.2 rounded-md bg-white/20 text-[10px]">
              {expectedFields.length}
            </span>
          </button>

          <button
            onClick={() => switchTab('coverage')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              activeTab === 'coverage'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800'
            }`}
          >
            <BarChart3 className="w-4 h-4" />
            <span>Coverage Analytics</span>
            {coverageData && (
              <span className="px-1.5 py-0.2 rounded-md bg-white/20 text-[10px]">
                {coverageData.coverage_score}%
              </span>
            )}
          </button>

          <button
            onClick={() => switchTab('analysis')}
            className={`flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer ${
              activeTab === 'analysis'
                ? 'bg-indigo-600 text-white shadow-sm'
                : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            <span>Autonomous Claims</span>
            <span className="text-[10px] text-amber-400 font-medium">(Coming Soon)</span>
          </button>
        </div>

        {/* ==================================================================== */}
        {/* TAB 1: RETRIEVED SOURCES */}
        {/* ==================================================================== */}
        {activeTab === 'sources' && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <Globe className="w-4 h-4 text-indigo-500" />
                  <span>Persisted Research Sources</span>
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Normalized and deduplicated web sources collected via Tavily Search and stored in Supabase.
                </p>
              </div>
              <span className="text-xs text-slate-400">
                {activeSources.length} verified reference{activeSources.length !== 1 ? 's' : ''}
              </span>
            </div>

            {isActiveSessionLoading ? (
              <div className="p-8 text-center">
                <Loader2 className="w-6 h-6 animate-spin text-indigo-500 mx-auto mb-2" />
                <p className="text-xs text-slate-400">Loading persisted sources...</p>
              </div>
            ) : activeSources.length === 0 ? (
              <Card className="p-8 text-center border-dashed">
                <div className="w-10 h-10 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-400 flex items-center justify-center mx-auto mb-3">
                  <Globe className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                  No sources recorded for this session
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-sm mx-auto">
                  The search query did not yield external web sources or Tavily timed out during execution.
                </p>
              </Card>
            ) : (
              <div className="grid grid-cols-1 gap-3.5">
                {activeSources.map((source, idx) => (
                  <Card key={source.id || idx} hover className="p-4 transition-all">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <a
                          href={source.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-sm font-semibold text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1.5"
                        >
                          <span className="truncate">{source.title || source.canonical_url}</span>
                          <ExternalLink className="w-3.5 h-3.5 shrink-0" />
                        </a>
                        <p className="text-[11px] text-slate-400 font-mono truncate mt-0.5">
                          {source.canonical_url || source.url}
                        </p>
                        {source.snippet && (
                          <p className="text-xs text-slate-600 dark:text-slate-300 mt-2 line-clamp-3 leading-relaxed">
                            {source.snippet}
                          </p>
                        )}
                      </div>

                      <div className="flex flex-col items-end gap-1.5 shrink-0">
                        {Array.isArray(source.providers) &&
                          source.providers.map((p) => (
                            <Badge
                              key={p}
                              variant={p === 'tavily' ? 'info' : 'neutral'}
                              size="sm"
                            >
                              {p === 'tavily' ? 'Tavily Search' : 'Custom URL'}
                            </Badge>
                          ))}
                        {source.score !== null && source.score !== undefined && (
                          <span className="text-[11px] font-medium text-slate-400">
                            Relevance: {Math.round(source.score * 100)}%
                          </span>
                        )}
                      </div>
                    </div>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 2: EXPECTED FIELDS & EVALUATION CRITERIA */}
        {/* ==================================================================== */}
        {activeTab === 'fields' && (
          <div className="space-y-4">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
              <div>
                <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <ListChecks className="w-4 h-4 text-indigo-500" />
                  <span>Expected Research Dimensions</span>
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Define research criteria and importance weights. Coverage status is managed through verified evidence.
                </p>
              </div>

              <div className="flex items-center gap-2">
                {expectedFields.length === 0 && (
                  <button
                    type="button"
                    onClick={handleLoadStarterFramework}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200 dark:border-indigo-800/80 hover:bg-indigo-100 transition-colors cursor-pointer"
                  >
                    <BookOpen className="w-3.5 h-3.5" />
                    <span>Load Starter Criteria</span>
                  </button>
                )}

                <button
                  type="button"
                  onClick={() => setIsAddFieldOpen(!isAddFieldOpen)}
                  className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-all cursor-pointer"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>Add Dimension</span>
                </button>
              </div>
            </div>

            {/* Error banner for field actions */}
            {fieldActionError && (
              <div className="p-3 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs flex items-center justify-between">
                <span>{fieldActionError}</span>
                <button onClick={() => setFieldActionError(null)} className="p-1">
                  <X className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Add Field Form Modal/Card */}
            {isAddFieldOpen && (
              <Card glow className="p-5 border-indigo-500/40 animate-in fade-in duration-200">
                <form onSubmit={handleCreateExpectedField} className="space-y-4">
                  <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
                    <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                      <Plus className="w-4 h-4 text-indigo-500" />
                      <span>New Research Dimension</span>
                    </h3>
                    <button
                      type="button"
                      onClick={() => setIsAddFieldOpen(false)}
                      className="p-1 text-slate-400 hover:text-white"
                    >
                      <X className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="sm:col-span-2">
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Dimension Name <span className="text-rose-400">*</span>
                      </label>
                      <input
                        type="text"
                        value={fieldName}
                        onChange={(e) => setFieldName(e.target.value)}
                        placeholder="e.g. Pricing Tiers & Free Tier Quotas"
                        required
                        className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:border-indigo-500"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Category
                      </label>
                      <input
                        type="text"
                        value={fieldCategory}
                        onChange={(e) => setFieldCategory(e.target.value)}
                        placeholder="e.g. Pricing, Security"
                        className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="sm:col-span-2">
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Evaluation Criteria / Description
                      </label>
                      <input
                        type="text"
                        value={fieldDescription}
                        onChange={(e) => setFieldDescription(e.target.value)}
                        placeholder="Specific questions or verification requirements to confirm this field..."
                        className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:border-indigo-500"
                      />
                    </div>

                    <div>
                      <label className="block text-xs font-medium text-slate-300 mb-1">
                        Importance Weight (0.10 - 5.00)
                      </label>
                      <input
                        type="number"
                        step="0.1"
                        min="0.1"
                        max="5.0"
                        value={fieldWeight}
                        onChange={(e) => setFieldWeight(e.target.value)}
                        className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-xl px-3 py-2 text-xs text-slate-900 dark:text-slate-100 focus:outline-none focus:border-indigo-500"
                      />
                    </div>
                  </div>

                  <div className="flex items-center justify-between pt-2">
                    <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={fieldRequired}
                        onChange={(e) => setFieldRequired(e.target.checked)}
                        className="rounded border-slate-700 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span>Strictly Required Dimension</span>
                    </label>

                    <div className="flex items-center gap-2">
                      <button
                        type="button"
                        onClick={() => setIsAddFieldOpen(false)}
                        className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-white"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        className="px-4 py-1.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white text-xs font-semibold shadow-sm"
                      >
                        Save Dimension
                      </button>
                    </div>
                  </div>
                </form>
              </Card>
            )}

            {/* List of Expected Fields */}
            {isFieldsLoading ? (
              <div className="p-8 text-center">
                <Loader2 className="w-6 h-6 animate-spin text-indigo-500 mx-auto mb-2" />
                <p className="text-xs text-slate-400">Loading expected dimensions...</p>
              </div>
            ) : expectedFields.length === 0 ? (
              <Card className="p-8 text-center border-dashed">
                <div className="w-10 h-10 rounded-xl bg-slate-100 dark:bg-slate-800 text-slate-400 flex items-center justify-center mx-auto mb-3">
                  <ListChecks className="w-5 h-5" />
                </div>
                <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                  No research dimensions defined yet
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 max-w-sm mx-auto">
                  Add custom expected dimensions to track completeness or load the starter evaluation framework.
                </p>
                <div className="mt-4 flex items-center justify-center gap-3">
                  <button
                    type="button"
                    onClick={handleLoadStarterFramework}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm cursor-pointer"
                  >
                    <BookOpen className="w-3.5 h-3.5" />
                    <span>Load Starter Framework</span>
                  </button>
                </div>
              </Card>
            ) : (
              <div className="space-y-3">
                {expectedFields.map((field) => {
                  const isEditing = editingFieldId === field.id;

                  if (isEditing) {
                    return (
                      <Card key={field.id} className="p-4 border-indigo-500/50">
                        <div className="space-y-3">
                          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                            <div className="sm:col-span-2">
                              <label className="block text-[11px] font-medium text-slate-400 mb-1">
                                Field Name
                              </label>
                              <input
                                type="text"
                                value={editFieldName}
                                onChange={(e) => setEditFieldName(e.target.value)}
                                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white"
                              />
                            </div>
                            <div>
                              <label className="block text-[11px] font-medium text-slate-400 mb-1">
                                Weight (0.10 - 5.00)
                              </label>
                              <input
                                type="number"
                                step="0.1"
                                min="0.1"
                                max="5.0"
                                value={editFieldWeight}
                                onChange={(e) => setEditFieldWeight(e.target.value)}
                                className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white"
                              />
                            </div>
                          </div>

                          <div>
                            <label className="block text-[11px] font-medium text-slate-400 mb-1">
                              Description
                            </label>
                            <input
                              type="text"
                              value={editFieldDescription}
                              onChange={(e) => setEditFieldDescription(e.target.value)}
                              className="w-full bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-white"
                            />
                          </div>

                          <div className="flex items-center justify-end gap-2 pt-1">
                            <button
                              type="button"
                              onClick={() => setEditingFieldId(null)}
                              className="px-2.5 py-1 text-xs text-slate-400 hover:text-white"
                            >
                              Cancel
                            </button>
                            <button
                              type="button"
                              onClick={() => handleSaveEditField(field.id)}
                              className="inline-flex items-center gap-1 px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold"
                            >
                              <Save className="w-3.5 h-3.5" />
                              <span>Update</span>
                            </button>
                          </div>
                        </div>
                      </Card>
                    );
                  }

                  return (
                    <Card key={field.id} hover className="p-4">
                      <div className="flex items-start justify-between gap-3">
                        <div className="min-w-0 flex-1">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold text-slate-900 dark:text-white">
                              {field.field_name}
                            </span>
                            <Badge variant="neutral" size="sm">
                              {field.field_category || 'General'}
                            </Badge>
                            <span className="text-[11px] text-slate-400 font-medium">
                              Weight: {Number(field.weight).toFixed(2)}x
                            </span>
                          </div>

                          {field.description && (
                            <p className="text-xs text-slate-500 dark:text-slate-400 mt-1.5 leading-relaxed">
                              {field.description}
                            </p>
                          )}
                        </div>

                        {/* Status Badge & Actions */}
                        <div className="flex items-center gap-2 shrink-0">
                          <Badge
                            variant={
                              field.status === 'covered'
                                ? 'success'
                                : field.status === 'partially_covered'
                                ? 'warning'
                                : 'danger'
                            }
                            size="sm"
                          >
                            {field.status === 'covered'
                              ? 'Covered'
                              : field.status === 'partially_covered'
                              ? 'Partial'
                              : 'Missing'}
                          </Badge>

                          <button
                            type="button"
                            onClick={() => handleStartEditField(field)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-400 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                            title="Edit Field"
                          >
                            <Edit3 className="w-3.5 h-3.5" />
                          </button>

                          <button
                            type="button"
                            onClick={() => handleDeleteField(field.id)}
                            className="p-1.5 rounded-lg text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors"
                            title="Delete Field"
                          >
                            <Trash2 className="w-3.5 h-3.5" />
                          </button>
                        </div>
                      </div>
                    </Card>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 3: REAL COVERAGE DASHBOARD & ANALYTICS */}
        {/* ==================================================================== */}
        {activeTab === 'coverage' && (
          <div className="space-y-6">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div>
                <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <BarChart3 className="w-4 h-4 text-indigo-500" />
                  <span>Research Coverage Dashboard</span>
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Calculated completeness score derived from defined criteria weights and evidence status.
                </p>
              </div>

              {coverageData && (
                <Badge
                  variant={
                    coverageData.coverage_score >= 75
                      ? 'success'
                      : coverageData.coverage_score >= 40
                      ? 'warning'
                      : 'danger'
                  }
                  size="md"
                >
                  Completeness: {coverageData.coverage_score}%
                </Badge>
              )}
            </div>

            {/* Coverage Explanation & Formula Alert */}
            <div className="p-4 rounded-2xl bg-indigo-500/10 dark:bg-indigo-950/40 border border-indigo-500/20 text-indigo-900 dark:text-indigo-200 text-xs space-y-1.5">
              <div className="flex items-center gap-2 font-semibold text-indigo-300">
                <Info className="w-4 h-4 text-indigo-400" />
                <span>How Coverage Score is Calculated</span>
              </div>
              <p className="text-slate-300 leading-relaxed">
                Coverage Score = (Weighted Points / Total Weight) &times; 100%. Covered criteria contribute 100% of their weight, partially covered criteria contribute 50%, and missing criteria contribute 0%.
              </p>
            </div>

            {/* Metrics Breakdown Cards */}
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
              <Card className="p-4 text-center">
                <span className="text-[11px] font-medium text-slate-400 uppercase tracking-wider">
                  Total Criteria
                </span>
                <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1">
                  {coverageData?.total_fields || 0}
                </p>
              </Card>

              <Card className="p-4 text-center">
                <span className="text-[11px] font-medium text-emerald-400 uppercase tracking-wider">
                  Covered (100%)
                </span>
                <p className="text-2xl font-bold text-emerald-400 mt-1">
                  {coverageData?.covered_fields || 0}
                </p>
              </Card>

              <Card className="p-4 text-center">
                <span className="text-[11px] font-medium text-amber-400 uppercase tracking-wider">
                  Partial (50%)
                </span>
                <p className="text-2xl font-bold text-amber-400 mt-1">
                  {coverageData?.partially_covered_fields || 0}
                </p>
              </Card>

              <Card className="p-4 text-center">
                <span className="text-[11px] font-medium text-rose-400 uppercase tracking-wider">
                  Missing (0%)
                </span>
                <p className="text-2xl font-bold text-rose-400 mt-1">
                  {coverageData?.missing_fields || 0}
                </p>
              </Card>
            </div>

            {/* Recharts Coverage by Category Chart */}
            {chartData.length > 0 ? (
              <Card className="p-6">
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
                  Completeness Depth by Category
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
                  Calculated weighted score for each research dimension group.
                </p>

                <div className="h-60 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <BarChart data={chartData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                      <XAxis dataKey="category" stroke="#94a3b8" fontSize={11} tickLine={false} />
                      <YAxis stroke="#94a3b8" fontSize={11} tickLine={false} domain={[0, 100]} />
                      <Tooltip
                        contentStyle={{
                          backgroundColor: '#0f172a',
                          borderColor: '#334155',
                          borderRadius: '12px',
                          fontSize: '12px',
                          color: '#f8fafc',
                        }}
                      />
                      <Bar dataKey="coverage" radius={[6, 6, 0, 0]}>
                        {chartData.map((entry, index) => (
                          <Cell key={`cell-${index}`} fill={entry.fill} />
                        ))}
                      </Bar>
                    </BarChart>
                  </ResponsiveContainer>
                </div>
              </Card>
            ) : (
              <Card className="p-8 text-center border-dashed">
                <p className="text-xs text-slate-400">
                  Define expected criteria in the "Expected Dimensions" tab to generate completeness charts.
                </p>
              </Card>
            )}
          </div>
        )}

        {/* ==================================================================== */}
        {/* TAB 4: AUTONOMOUS CLAIMS (TRANSPARENT COMING SOON STATUS) */}
        {/* ==================================================================== */}
        {activeTab === 'analysis' && (
          <div className="space-y-4">
            <Card className="p-8 text-center border-dashed">
              <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 border border-indigo-500/20 text-indigo-400 flex items-center justify-center mx-auto mb-4">
                <Sparkles className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Autonomous Claim Extraction & Semantic Discrepancy Hub
              </h3>
              <Badge variant="warning" size="sm" className="mt-2">
                Under Active Development
              </Badge>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-3 max-w-lg mx-auto leading-relaxed">
                InfoScope AI's LLM-driven claim extraction and contradiction detection pipeline is scheduled for release in the next milestone. In accordance with strict data integrity rules, this platform avoids generating synthetic claims or fabricated conflict reports.
              </p>
              <p className="text-[11px] text-slate-400 mt-2">
                Web sources retrieved via Tavily and expected criteria evaluation are fully operational.
              </p>
            </Card>
          </div>
        )}
      </div>
    );
  }

  // ============================================================================
  // RENDER: DASHBOARD HOME (NEW RESEARCH + RECENT SESSIONS)
  // ============================================================================
  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Header Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-200 dark:border-slate-800/80">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              AI Information Gap Detector
            </h1>
            <Badge variant="primary" size="sm">
              Production MVP
            </Badge>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Detect missing information, conflicting claims, and source coverage across web intelligence.
          </p>
        </div>

        {/* Quick Help Badge */}
        <div className="flex items-center gap-2">
          <Badge variant="info" size="sm">
            Tavily Web Intelligence Active
          </Badge>
        </div>
      </div>

      {/* Feature Pillar Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        <Card hover className="p-6 relative overflow-hidden group">
          <div className="w-11 h-11 rounded-xl bg-blue-500/10 dark:bg-blue-950/50 border border-blue-500/20 text-blue-500 dark:text-blue-400 flex items-center justify-center mb-4 transition-transform group-hover:scale-105">
            <Globe className="w-5 h-5" />
          </div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white flex items-center justify-between">
            <span>Multi-Source Research</span>
            <Badge variant="info" size="sm">Dual Search</Badge>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 leading-relaxed">
            Ingests both live web search indices via Tavily and custom target URLs to extract grounded sources and citations.
          </p>
        </Card>

        <Card hover className="p-6 relative overflow-hidden group">
          <div className="w-11 h-11 rounded-xl bg-amber-500/10 dark:bg-amber-950/50 border border-amber-500/20 text-amber-500 dark:text-amber-400 flex items-center justify-center mb-4 transition-transform group-hover:scale-105">
            <ListChecks className="w-5 h-5" />
          </div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white flex items-center justify-between">
            <span>Expected Criteria Engine</span>
            <Badge variant="warning" size="sm">Weighted Scoring</Badge>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 leading-relaxed">
            Define weighted research dimensions to track information completeness across architecture, pricing, and security.
          </p>
        </Card>

        <Card hover className="p-6 relative overflow-hidden group">
          <div className="w-11 h-11 rounded-xl bg-indigo-500/10 dark:bg-indigo-950/50 border border-indigo-500/20 text-indigo-500 dark:text-indigo-400 flex items-center justify-center mb-4 transition-transform group-hover:scale-105">
            <BarChart3 className="w-5 h-5" />
          </div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white flex items-center justify-between">
            <span>Coverage Analytics</span>
            <Badge variant="primary" size="sm">Supabase RLS</Badge>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 leading-relaxed">
            Persistent sessions and completeness dashboards stored securely with Row Level Security in Supabase PostgreSQL.
          </p>
        </Card>
      </div>

      {/* Main Research Input Panel */}
      <Card glow className="p-6 sm:p-8">
        <form onSubmit={handleStartAnalysis} className="space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Search className="w-5 h-5 text-indigo-500" />
                <span>New Research Investigation</span>
              </h2>
              <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                Formulate a clear topic, technical assertion, or query for comprehensive cross-source analysis.
              </p>
            </div>

            {/* Source Strategy Pills */}
            <div className="flex items-center p-1 rounded-xl bg-slate-100 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/60 self-start sm:self-auto">
              <button
                type="button"
                onClick={() => setSourceStrategy('web')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  sourceStrategy === 'web'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Globe className="w-3.5 h-3.5" />
                <span>Web Search</span>
              </button>

              <button
                type="button"
                onClick={() => setSourceStrategy('urls')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  sourceStrategy === 'urls'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Link2 className="w-3.5 h-3.5" />
                <span>My URLs</span>
              </button>

              <button
                type="button"
                onClick={() => setSourceStrategy('both')}
                className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
                  sourceStrategy === 'both'
                    ? 'bg-indigo-600 text-white shadow-sm'
                    : 'text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white'
                }`}
              >
                <Layers className="w-3.5 h-3.5" />
                <span>Both</span>
              </button>
            </div>
          </div>

          {/* Web Search Provider Engine: Tavily */}
          {(sourceStrategy === 'web' || sourceStrategy === 'both') && (
            <div className="p-3.5 rounded-2xl bg-slate-50 dark:bg-slate-950/60 border border-slate-200 dark:border-slate-800/80 flex flex-col sm:flex-row sm:items-center justify-between gap-3 animate-in fade-in duration-200">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-xl bg-indigo-500/10 dark:bg-indigo-950/60 border border-indigo-500/20 text-indigo-500 dark:text-indigo-400 flex items-center justify-center shrink-0">
                  <Cpu className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-semibold text-slate-900 dark:text-slate-100">
                      Search Provider Engine
                    </span>
                    <Badge variant="primary" size="sm">Tavily</Badge>
                  </div>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 mt-0.5">
                    Grounded real-time web search powered by Tavily Search API.
                  </p>
                </div>
              </div>

              <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-xl bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-200 dark:border-indigo-800/60 text-indigo-700 dark:text-indigo-300 text-xs font-medium self-start sm:self-auto">
                <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse"></span>
                <span>Tavily Search API Connected</span>
              </div>
            </div>
          )}

          {/* Research Query Input */}
          <div>
            <textarea
              id="research-query-textarea"
              rows={3}
              value={researchQuery}
              onChange={(e) => setResearchQuery(e.target.value)}
              placeholder="e.g. Compare Supabase Auth vs AWS Cognito architecture, pricing changes, and multi-tenant capabilities in 2026."
              required
              className="w-full bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all resize-none"
            />
          </div>

          {/* Sample Topic Quick Pill */}
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-slate-400">Quick Start Examples:</span>
            <button
              type="button"
              onClick={() => {
                setResearchQuery('Compare Supabase Auth vs Auth0 for multi-tenant SaaS architecture');
                setSourceStrategy('both');
              }}
              className="text-xs px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-indigo-500 hover:text-indigo-400 border border-slate-200 dark:border-slate-700 font-medium cursor-pointer"
            >
              Supabase Auth vs Auth0
            </button>
            <button
              type="button"
              onClick={() => {
                setResearchQuery('FastAPI vs Go Gin performance benchmarks and microservice architectures');
                setSourceStrategy('web');
              }}
              className="text-xs px-2.5 py-1 rounded-lg bg-slate-100 dark:bg-slate-800 text-indigo-500 hover:text-indigo-400 border border-slate-200 dark:border-slate-700 font-medium cursor-pointer"
            >
              FastAPI vs Go Gin
            </button>
          </div>

          {/* Custom URLs Section (Conditional) */}
          {(sourceStrategy === 'urls' || sourceStrategy === 'both') && (
            <div className="space-y-3 pt-2 border-t border-slate-100 dark:border-slate-800/80 animate-in fade-in duration-200">
              <div className="flex items-center justify-between">
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                  <Link2 className="w-3.5 h-3.5 text-indigo-400" />
                  <span>Target Custom URLs (Up to 5 sources)</span>
                </label>
                {customUrls.length < 5 && (
                  <button
                    type="button"
                    onClick={handleAddUrl}
                    className="inline-flex items-center gap-1 text-xs font-semibold text-indigo-500 hover:text-indigo-400 cursor-pointer"
                  >
                    <Plus className="w-3.5 h-3.5" />
                    <span>Add URL</span>
                  </button>
                )}
              </div>

              <div className="space-y-2">
                {customUrls.map((url, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <input
                      type="url"
                      value={url}
                      onChange={(e) => handleUpdateUrl(idx, e.target.value)}
                      placeholder="https://docs.example.com/specifications/v2"
                      className="flex-1 bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 rounded-xl px-3.5 py-2 text-xs text-slate-800 dark:text-slate-200 placeholder-slate-400 dark:placeholder-slate-600 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-all"
                    />
                    <button
                      type="button"
                      onClick={() => handleRemoveUrl(idx)}
                      disabled={customUrls.length === 1 && !url}
                      className="p-2 rounded-xl text-slate-400 hover:text-rose-400 hover:bg-rose-500/10 transition-colors disabled:opacity-30 cursor-pointer"
                      title="Remove URL"
                    >
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Submission Error Banner */}
          {submissionError && (
            <div className="p-4 rounded-xl bg-rose-500/10 border border-rose-500/20 text-rose-300 text-xs space-y-1">
              <div className="flex items-center gap-2 font-semibold">
                <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0" />
                <span>Research Initialization Failed</span>
              </div>
              <p>{submissionError}</p>
              {diagnosticInfo?.suggestedAction && (
                <p className="text-[11px] text-slate-400 mt-1 font-mono">
                  Suggested Action: {diagnosticInfo.suggestedAction}
                </p>
              )}
            </div>
          )}

          {/* Action Row */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Info className="w-4 h-4 text-indigo-400 shrink-0" />
              <span>Grounded sources and criteria will be persisted to your Supabase session.</span>
            </div>

            <button
              type="submit"
              id="analyze-gaps-button"
              disabled={isAnalyzing || !researchQuery.trim()}
              className="w-full sm:w-auto px-6 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-medium text-sm flex items-center justify-center gap-2 shadow-lg shadow-indigo-600/25 transition-all disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
            >
              {isAnalyzing ? (
                <>
                  <div className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  <span>Scanning Tavily & Persisting Sources...</span>
                </>
              ) : (
                <>
                  <Sparkles className="w-4 h-4" />
                  <span>Analyze Information Gaps</span>
                </>
              )}
            </button>
          </div>
        </form>
      </Card>

      {/* ==================================================================== */}
      {/* RESEARCH HISTORY SECTION (PERSISTED SUPABASE SESSIONS) */}
      {/* ==================================================================== */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Clock className="w-5 h-5 text-indigo-500" />
              <span>Recent Research Sessions</span>
            </h2>
            <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
              Reopen previous investigations and review source coverage.
            </p>
          </div>

          <button
            type="button"
            onClick={() => refetchSessions()}
            className="p-1.5 rounded-xl text-slate-400 hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            title="Refresh Sessions List"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>

        {/* Loading State */}
        {isSessionsLoading ? (
          <div className="p-8 text-center">
            <Loader2 className="w-6 h-6 animate-spin text-indigo-500 mx-auto mb-2" />
            <p className="text-xs text-slate-400">Loading research history from Supabase...</p>
          </div>
        ) : isSessionsError ? (
          <Card className="p-6 text-center border-rose-500/30">
            <AlertTriangle className="w-6 h-6 text-rose-400 mx-auto mb-2" />
            <p className="text-xs text-rose-300">Failed to load research history.</p>
            <button
              onClick={() => refetchSessions()}
              className="mt-3 text-xs text-indigo-400 underline"
            >
              Retry
            </button>
          </Card>
        ) : sessionList.length === 0 ? (
          <Card className="p-10 text-center border-dashed border-2">
            <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/60 text-slate-400 mx-auto flex items-center justify-center mb-3">
              <Search className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
              No previous research sessions recorded
            </h3>
            <p className="max-w-md mx-auto text-xs text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
              Submit your first research query above to begin investigating information gaps across web sources.
            </p>
          </Card>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {sessionList.map((session) => {
              const formattedDate = session.created_at
                ? new Date(session.created_at).toLocaleDateString(undefined, {
                    month: 'short',
                    day: 'numeric',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  })
                : 'Recent';

              return (
                <Card
                  key={session.id}
                  hover
                  onClick={() => selectSession(session.id)}
                  className="p-5 cursor-pointer flex flex-col justify-between transition-all group"
                >
                  <div>
                    <div className="flex items-start justify-between gap-3">
                      <h3 className="text-sm font-semibold text-slate-900 dark:text-white group-hover:text-indigo-400 transition-colors line-clamp-1">
                        {session.title || 'Untitled Session'}
                      </h3>
                      <Badge
                        variant={
                          session.status === 'completed'
                            ? 'success'
                            : session.status === 'failed'
                            ? 'danger'
                            : 'primary'
                        }
                        size="sm"
                      >
                        {session.status || 'Active'}
                      </Badge>
                    </div>

                    <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">
                      "{session.research_query}"
                    </p>
                  </div>

                  <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-[11px] text-slate-400">
                    <span className="flex items-center gap-1.5">
                      <Clock className="w-3.5 h-3.5" />
                      <span>{formattedDate}</span>
                    </span>

                    <div className="flex items-center gap-2 font-medium text-indigo-500 group-hover:translate-x-0.5 transition-transform">
                      <span>Open Investigation</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};
