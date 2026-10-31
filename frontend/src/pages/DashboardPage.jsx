import React, { useState } from 'react';
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
  Compass,
  ArrowUpRight,
  ShieldAlert,
} from 'lucide-react';
import {
  ResponsiveContainer,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  Cell,
  PieChart,
  Pie,
} from 'recharts';

export const DashboardPage = () => {
  const { user, isDemoUser } = useAuth();

  // Research input state
  const [researchQuery, setResearchQuery] = useState('');
  const [sourceStrategy, setSourceStrategy] = useState('both'); // 'web', 'urls', 'both'
  const [customUrls, setCustomUrls] = useState(['']);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [showSampleData, setShowSampleData] = useState(false);
  const [submittedQuery, setSubmittedQuery] = useState(null);

  // URL management
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

  // Submit trigger simulation
  const handleStartAnalysis = (e) => {
    e.preventDefault();
    if (!researchQuery.trim()) return;

    setIsAnalyzing(true);
    setSubmittedQuery({
      query: researchQuery,
      strategy: sourceStrategy,
      urls: customUrls.filter((u) => u.trim() !== ''),
      timestamp: new Date().toLocaleTimeString(),
    });

    setTimeout(() => {
      setIsAnalyzing(false);
      setShowSampleData(true);
    }, 1200);
  };

  // Sample data for Recharts coverage metrics
  const coverageData = [
    { category: 'Technical Specs', coverage: 88, fill: '#6366f1' },
    { category: 'Pricing & Tiers', coverage: 42, fill: '#f59e0b' },
    { category: 'Privacy & Security', coverage: 74, fill: '#3b82f6' },
    { category: 'Roadmap & Recency', coverage: 31, fill: '#ef4444' },
    { category: 'Customer Feedback', coverage: 92, fill: '#10b981' },
  ];

  const breakdownData = [
    { name: 'Verified Claims', value: 18, color: '#10b981' },
    { name: 'Conflicting Claims', value: 4, color: '#f59e0b' },
    { name: 'Information Gaps', value: 6, color: '#6366f1' },
    { name: 'Outdated Sources', value: 3, color: '#ef4444' },
  ];

  return (
    <div className="max-w-7xl mx-auto space-y-8">
      {/* Welcome Banner */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-slate-200 dark:border-slate-800/80">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 dark:text-white">
              AI Information Gap Detector
            </h1>
            <Badge variant="primary" size="sm">
              Production Foundation
            </Badge>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Detect missing information, conflicting claims, and source staleness across web intelligence.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setShowSampleData(!showSampleData)}
            className="inline-flex items-center gap-2 px-3.5 py-2 rounded-xl text-xs font-semibold border transition-all cursor-pointer bg-white dark:bg-slate-900 border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:border-indigo-500 hover:text-indigo-500"
          >
            <Compass className="w-4 h-4 text-indigo-400" />
            <span>{showSampleData ? 'Hide Sample Preview' : 'Toggle Sample Preview UI'}</span>
          </button>
        </div>
      </div>

      {/* Feature Pillar Overview Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-5">
        {/* Card 1: Multi-source Research */}
        <Card hover className="p-6 relative overflow-hidden group">
          <div className="w-11 h-11 rounded-xl bg-blue-500/10 dark:bg-blue-950/50 border border-blue-500/20 text-blue-500 dark:text-blue-400 flex items-center justify-center mb-4 transition-transform group-hover:scale-105">
            <Globe className="w-5 h-5" />
          </div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white flex items-center justify-between">
            <span>Multi-Source Research</span>
            <Badge variant="info" size="sm">Dual Search</Badge>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 leading-relaxed">
            Ingests both live web search indices and custom target URLs to extract grounded claims and citations.
          </p>
          <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
            <span>Web + URL Engine</span>
            <span className="text-blue-500 dark:text-blue-400 font-medium">Automatic Ingestion</span>
          </div>
        </Card>

        {/* Card 2: Conflict Detection */}
        <Card hover className="p-6 relative overflow-hidden group">
          <div className="w-11 h-11 rounded-xl bg-amber-500/10 dark:bg-amber-950/50 border border-amber-500/20 text-amber-500 dark:text-amber-400 flex items-center justify-center mb-4 transition-transform group-hover:scale-105">
            <AlertTriangle className="w-5 h-5" />
          </div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white flex items-center justify-between">
            <span>Conflict Detection</span>
            <Badge variant="warning" size="sm">Cross-Check</Badge>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 leading-relaxed">
            Flags contradictory statements between opposing documentation, vendor claims, and community reports.
          </p>
          <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
            <span>Discrepancy Analyzer</span>
            <span className="text-amber-500 dark:text-amber-400 font-medium">Claim Contradictions</span>
          </div>
        </Card>

        {/* Card 3: Information Gaps */}
        <Card hover className="p-6 relative overflow-hidden group">
          <div className="w-11 h-11 rounded-xl bg-indigo-500/10 dark:bg-indigo-950/50 border border-indigo-500/20 text-indigo-500 dark:text-indigo-400 flex items-center justify-center mb-4 transition-transform group-hover:scale-105">
            <FileQuestion className="w-5 h-5" />
          </div>
          <h2 className="text-base font-semibold text-slate-900 dark:text-white flex items-center justify-between">
            <span>Information Gaps</span>
            <Badge variant="primary" size="sm">Checklists</Badge>
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-2 leading-relaxed">
            Pinpoints unaddressed research questions and automatically compiles prioritized verification tasks.
          </p>
          <div className="mt-4 pt-3 border-t border-slate-100 dark:border-slate-800/80 flex items-center justify-between text-[11px] text-slate-400">
            <span>Missing Evidence</span>
            <span className="text-indigo-500 dark:text-indigo-400 font-medium">Prioritized Actions</span>
          </div>
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

          {/* Research Query Input */}
          <div>
            <textarea
              id="research-query-textarea"
              rows={3}
              value={researchQuery}
              onChange={(e) => setResearchQuery(e.target.value)}
              placeholder="e.g. What are the key architectural differences and pricing changes between Supabase Auth v2 and AWS Cognito in 2026?"
              required
              className="w-full bg-slate-50 dark:bg-slate-950/80 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 text-sm text-slate-900 dark:text-slate-100 placeholder-slate-400 dark:placeholder-slate-500 focus:outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-500/20 transition-all resize-none"
            />
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

          {/* Action Row */}
          <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3">
            <div className="flex items-center gap-2 text-xs text-slate-400">
              <Info className="w-4 h-4 text-indigo-400 shrink-0" />
              <span>Multi-perspective cross-examination will organize verifiable evidence.</span>
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
                  <span>Scanning Sources & Identifying Gaps...</span>
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

      {/* SAMPLE DATA SECTION (Clearly Distinguished) */}
      {showSampleData && (
        <div className="space-y-6 animate-in fade-in slide-in-from-top-4 duration-300">
          {/* Sample Data Alert Header */}
          <div className="p-4 rounded-2xl bg-indigo-500/10 dark:bg-indigo-950/40 border border-indigo-500/20 text-indigo-900 dark:text-indigo-200 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <Compass className="w-5 h-5 text-indigo-500 dark:text-indigo-400 shrink-0" />
              <div>
                <span className="font-semibold text-xs tracking-wide uppercase px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-400 border border-indigo-500/30 mr-2">
                  Sample Data — For Demo Preview
                </span>
                <span className="text-xs text-slate-600 dark:text-slate-300 font-medium">
                  {submittedQuery ? `Query: "${submittedQuery.query}"` : 'Demonstrating future AI engine output'}
                </span>
              </div>
            </div>
            <span className="text-[11px] text-slate-400">Mock Data / UI Prototype View</span>
          </div>

          {/* Coverage Score & Metrics Grid */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Chart: Category Coverage */}
            <Card className="p-6 lg:col-span-2">
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                    <BarChart3 className="w-4 h-4 text-indigo-500" />
                    <span>Coverage Depth by Research Dimension</span>
                  </h3>
                  <p className="text-xs text-slate-500 dark:text-slate-400">
                    Calculated percentage of factual corroboration across verified sources.
                  </p>
                </div>
                <Badge variant="primary" size="sm">Score: 68/100</Badge>
              </div>

              <div className="h-56 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={coverageData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                    <XAxis
                      dataKey="category"
                      stroke="#94a3b8"
                      fontSize={11}
                      tickLine={false}
                    />
                    <YAxis
                      stroke="#94a3b8"
                      fontSize={11}
                      tickLine={false}
                      domain={[0, 100]}
                    />
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
                      {coverageData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={entry.fill} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </Card>

            {/* Breakdown Status Card */}
            <Card className="p-6 flex flex-col justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-900 dark:text-white mb-1">
                  Claim Status Breakdown
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mb-4">
                  Extracted from 14 references.
                </p>

                <div className="space-y-3">
                  {breakdownData.map((item) => (
                    <div key={item.name} className="flex items-center justify-between text-xs">
                      <span className="flex items-center gap-2 text-slate-600 dark:text-slate-300">
                        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: item.color }} />
                        {item.name}
                      </span>
                      <span className="font-semibold text-slate-900 dark:text-white">{item.value} items</span>
                    </div>
                  ))}
                </div>
              </div>

              <div className="mt-6 pt-4 border-t border-slate-100 dark:border-slate-800">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Overall Reliability</span>
                  <Badge variant="success" size="sm">High Confidence</Badge>
                </div>
              </div>
            </Card>
          </div>

          {/* Detected Conflicts and Gaps Cards */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Detected Conflict Sample */}
            <Card className="p-6 border-l-4 border-l-amber-500">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-amber-500" />
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                    Conflicting Claim Detected
                  </h3>
                </div>
                <Badge variant="warning" size="sm">High Divergence</Badge>
              </div>
              <p className="text-xs font-semibold text-slate-700 dark:text-slate-200 mb-2">
                Discrepancy: Rate limit policies on free tier vs enterprise plans.
              </p>
              <div className="space-y-2 text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-950/60 p-3 rounded-xl border border-slate-200 dark:border-slate-800">
                <p><strong className="text-indigo-400">Source A (Official Docs):</strong> Claims up to 500 requests/sec with burst tolerance.</p>
                <p><strong className="text-amber-400">Source B (Community Benchmark):</strong> Reports throttles occurring at ~120 requests/sec under load.</p>
              </div>
            </Card>

            {/* Information Gap Sample */}
            <Card className="p-6 border-l-4 border-l-rose-500">
              <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                  <FileQuestion className="w-4 h-4 text-rose-500" />
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                    Missing Information Gap
                  </h3>
                </div>
                <Badge variant="danger" size="sm">Missing Evidence</Badge>
              </div>
              <p className="text-xs font-semibold text-slate-700 dark:text-slate-200 mb-2">
                Gap: No clear statement on HIPAA compliance certification for 2026.
              </p>
              <div className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-950/60 p-3 rounded-xl border border-slate-200 dark:border-slate-800">
                <p>None of the crawled primary sources or linked URLs address HIPAA or BAA agreements for the latest release cycle.</p>
                <p className="mt-1 font-medium text-indigo-400">Recommended Action: Direct inquiry to vendor compliance team.</p>
              </div>
            </Card>
          </div>
        </div>
      )}

      {/* Research History / Empty State */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            Recent Research Sessions
          </h2>
          <span className="text-xs text-slate-400">Supabase RLS Protected</span>
        </div>

        {/* Clean Empty State */}
        {!showSampleData ? (
          <Card className="p-10 text-center border-dashed border-2">
            <div className="w-12 h-12 rounded-2xl bg-slate-100 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700/60 text-slate-400 mx-auto flex items-center justify-center mb-3">
              <Search className="w-6 h-6" />
            </div>
            <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
              No previous research sessions recorded
            </h3>
            <p className="max-w-md mx-auto text-xs text-slate-500 dark:text-slate-400 mt-1 leading-relaxed">
              Submit your first research query above or enable the sample preview toggle to see the evidence analysis interface in action.
            </p>
            <div className="mt-4">
              <button
                onClick={() => {
                  setResearchQuery('Compare Supabase Auth vs Auth0 for multi-tenant SaaS');
                  setSourceStrategy('both');
                }}
                className="text-xs text-indigo-500 hover:text-indigo-400 font-semibold cursor-pointer"
              >
                Insert sample query into search &rarr;
              </button>
            </div>
          </Card>
        ) : (
          <Card className="p-4 divide-y divide-slate-100 dark:divide-slate-800">
            <div className="py-3 flex items-center justify-between">
              <div>
                <p className="text-xs font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                  <span>{submittedQuery?.query || 'Supabase Auth vs AWS Cognito Architecture Evaluation'}</span>
                  <Badge variant="primary" size="sm">Sample</Badge>
                </p>
                <p className="text-[11px] text-slate-400 mt-0.5">
                  Sources: Web + 2 URLs &bull; Status: Completed &bull; Coverage: 68%
                </p>
              </div>
              <button
                onClick={() => setShowSampleData(true)}
                className="p-1.5 rounded-lg text-slate-400 hover:text-indigo-400 hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
};
