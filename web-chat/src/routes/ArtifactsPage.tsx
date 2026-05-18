import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { AppShell } from '@/components/layout/AppShell';
import { useTasksStore } from '@/stores/tasksStore';
import { useTaskStream } from '@/hooks/useTaskStream';
import { apiFetch } from '@/lib/api';

// ── Types ────────────────────────────────────────────────────────────────────

interface ArtifactRecord {
  artifact_id: string;
  task_id: string;
  pipeline_id: string | null;
  kind: string;
  filename: string;
  label_ar: string;
  mime_type: string;
  size_bytes: number;
  language: string | null;
  created_at: string;
}

type ArtifactKind =
  | 'md' | 'html' | 'code' | 'mermaid' | 'pdf'
  | 'zip' | 'json' | 'screenshot' | 'csv' | 'all';

// ── Helpers ───────────────────────────────────────────────────────────────────

const KIND_ICON: Record<string, string> = {
  md: '📄', html: '🌐', code: '💻', mermaid: '📊',
  pdf: '📕', zip: '📦', json: '{ }', screenshot: '📸', csv: '📋',
};

const PREVIEWABLE = new Set(['md', 'html', 'code', 'mermaid', 'json', 'csv', 'screenshot']);

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / (1024 * 1024)).toFixed(1)} MB`;
}

function fmtDate(iso: string): string {
  try {
    return new Date(iso).toLocaleString('ar-EG', {
      day: '2-digit', month: '2-digit', year: '2-digit',
      hour: '2-digit', minute: '2-digit',
    });
  } catch {
    return iso;
  }
}

// ── Preview Modal ─────────────────────────────────────────────────────────────

function PreviewModal({
  artifact,
  onClose,
}: {
  artifact: ArtifactRecord;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [content, setContent] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const url = `/api/artifacts/${artifact.artifact_id}/preview`;
    fetch(url)
      .then((r) => {
        if (!r.ok) throw new Error(r.statusText);
        if (artifact.kind === 'screenshot') return r.blob().then((b) => URL.createObjectURL(b));
        return r.text();
      })
      .then((v) => { if (!cancelled) setContent(v as string); })
      .catch((e: unknown) => { if (!cancelled) setError(e instanceof Error ? e.message : 'خطأ'); })
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, [artifact.artifact_id, artifact.kind]);

  // Close on Escape
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', h);
    return () => window.removeEventListener('keydown', h);
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4" role="dialog" aria-modal>
      {/* Backdrop */}
      <div
        className="absolute inset-0 bg-black/50 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* Panel */}
      <div className="relative z-10 w-full max-w-3xl max-h-[80vh] flex flex-col rounded-2xl bg-white dark:bg-slate-900 shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="flex items-center gap-3 px-5 py-3 border-b border-slate-100 dark:border-slate-800">
          <span className="text-xl">{KIND_ICON[artifact.kind] ?? '📁'}</span>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{artifact.label_ar}</p>
            <p className="text-xs text-slate-400 truncate">{artifact.filename}</p>
          </div>
          <a
            href={`/api/artifacts/${artifact.artifact_id}/download`}
            download={artifact.filename}
            className="px-3 py-1 text-xs rounded-lg bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-900/30 dark:hover:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 transition-colors"
          >
            {t('artifacts.download')}
          </a>
          <button
            onClick={onClose}
            aria-label={t('artifacts.close')}
            className="w-7 h-7 flex items-center justify-center rounded-full text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 text-sm transition-colors"
          >
            ✕
          </button>
        </div>

        {/* Body */}
        <div className="flex-1 overflow-auto p-4">
          {loading && (
            <div className="flex items-center justify-center h-32 text-slate-400 text-sm animate-pulse">
              ⏳ {t('artifacts.loading')}
            </div>
          )}
          {error && (
            <p className="text-rose-500 text-sm text-center py-8">{error}</p>
          )}
          {!loading && !error && content && (
            <>
              {artifact.kind === 'screenshot' ? (
                <img src={content} alt={artifact.label_ar} className="max-w-full rounded-lg" />
              ) : artifact.kind === 'html' ? (
                <iframe
                  srcDoc={content}
                  sandbox="allow-scripts"
                  className="w-full h-96 border border-slate-200 dark:border-slate-700 rounded-lg bg-white"
                  title={artifact.label_ar}
                />
              ) : (
                <pre className="text-xs leading-relaxed text-slate-700 dark:text-slate-300 whitespace-pre-wrap font-mono overflow-auto max-h-96">
                  {content}
                </pre>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Artifact Card ─────────────────────────────────────────────────────────────

function ArtifactCard({
  artifact,
  onPreview,
}: {
  artifact: ArtifactRecord;
  onPreview: (a: ArtifactRecord) => void;
}) {
  const { t } = useTranslation();
  const canPreview = PREVIEWABLE.has(artifact.kind);

  return (
    <div className="flex flex-col rounded-xl border border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-sm hover:shadow-md transition-shadow overflow-hidden">
      {/* Top colour strip by kind */}
      <div className={`h-1 ${kindColor(artifact.kind)}`} />

      <div className="flex items-start gap-3 p-4">
        <span className="text-2xl leading-none mt-0.5 select-none">
          {KIND_ICON[artifact.kind] ?? '📁'}
        </span>
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-slate-800 dark:text-slate-200 truncate">{artifact.label_ar}</p>
          <p className="text-xs text-slate-400 truncate mt-0.5">{artifact.filename}</p>
          {artifact.language && (
            <span className="inline-block mt-1 px-1.5 py-0.5 text-[10px] rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
              {artifact.language}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between px-4 pb-3 mt-auto">
        <div className="text-[11px] text-slate-400 space-y-0.5">
          <p>{fmtBytes(artifact.size_bytes)}</p>
          <p>{fmtDate(artifact.created_at)}</p>
        </div>
        <div className="flex items-center gap-2">
          {canPreview && (
            <button
              onClick={() => onPreview(artifact)}
              className="px-2.5 py-1 text-xs rounded-lg bg-slate-50 hover:bg-slate-100 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-600 dark:text-slate-300 transition-colors"
            >
              {t('artifacts.preview')}
            </button>
          )}
          <a
            href={`/api/artifacts/${artifact.artifact_id}/download`}
            download={artifact.filename}
            className="px-2.5 py-1 text-xs rounded-lg bg-indigo-50 hover:bg-indigo-100 dark:bg-indigo-900/30 dark:hover:bg-indigo-900/50 text-indigo-700 dark:text-indigo-300 transition-colors"
          >
            {t('artifacts.download')}
          </a>
        </div>
      </div>
    </div>
  );
}

function kindColor(kind: string): string {
  const map: Record<string, string> = {
    md: 'bg-blue-400', html: 'bg-orange-400', code: 'bg-purple-400',
    mermaid: 'bg-teal-400', pdf: 'bg-red-400', zip: 'bg-yellow-400',
    json: 'bg-green-400', screenshot: 'bg-pink-400', csv: 'bg-cyan-400',
  };
  return map[kind] ?? 'bg-slate-400';
}

// ── Filter Bar ────────────────────────────────────────────────────────────────

const ALL_KINDS: ArtifactKind[] = ['all', 'md', 'html', 'code', 'mermaid', 'pdf', 'zip', 'json', 'screenshot', 'csv'];

function FilterBar({
  activeKind,
  available,
  onChange,
}: {
  activeKind: ArtifactKind;
  available: Set<string>;
  onChange: (k: ArtifactKind) => void;
}) {
  const { t } = useTranslation();
  const filters = ALL_KINDS.filter((k) => k === 'all' || available.has(k));
  if (filters.length <= 1) return null;

  return (
    <div className="flex gap-2 flex-wrap mb-4">
      {filters.map((k) => (
        <button
          key={k}
          onClick={() => onChange(k)}
          className={`px-3 py-1 text-xs rounded-full border transition-colors ${
            activeKind === k
              ? 'bg-indigo-600 text-white border-indigo-600'
              : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-indigo-400'
          }`}
        >
          {k === 'all'
            ? t('artifacts.filterAll')
            : `${KIND_ICON[k] ?? ''} ${t(`artifacts.kinds.${k}` as Parameters<typeof t>[0])}`}
        </button>
      ))}
    </div>
  );
}

// ── Main Page ─────────────────────────────────────────────────────────────────

export default function ArtifactsPage() {
  const { t } = useTranslation();
  const { tasks, activeTaskId } = useTasksStore();
  const stream = useTaskStream(null);

  const [artifacts, setArtifacts] = useState<ArtifactRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [activeKind, setActiveKind] = useState<ArtifactKind>('all');
  const [preview, setPreview] = useState<ArtifactRecord | null>(null);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const data = await apiFetch<ArtifactRecord[]>('/api/artifacts');
      setArtifacts(data);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : t('artifacts.loadError'));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => {
    void load();
    // Poll every 10 s so new artifacts appear without manual refresh
    intervalRef.current = setInterval(() => void load(), 10_000);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [load]);

  const available = new Set(artifacts.map((a) => a.kind));
  const visible = activeKind === 'all'
    ? artifacts
    : artifacts.filter((a) => a.kind === activeKind);

  return (
    <AppShell
      tasks={tasks}
      activeTaskId={activeTaskId}
      taskStream={stream}
      onNewChat={() => {}}
      onSelectTask={() => {}}
    >
      <div className="max-w-5xl mx-auto px-4 py-8">
        {/* Header */}
        <div className="flex items-center justify-between mb-6">
          <h1 className="text-2xl font-semibold text-slate-800 dark:text-slate-200">
            {t('artifacts.title')}
          </h1>
          <button
            onClick={() => { setLoading(true); void load(); }}
            disabled={loading}
            aria-label={t('artifacts.refresh')}
            className="px-3 py-1.5 text-sm rounded-lg border border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:border-indigo-400 hover:text-indigo-600 disabled:opacity-50 transition-colors"
          >
            {loading ? '⏳' : '🔄'} {t('artifacts.refresh')}
          </button>
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 p-3 rounded-xl bg-rose-50 dark:bg-rose-950/30 border border-rose-200 dark:border-rose-900 text-rose-700 dark:text-rose-400 text-sm">
            {error}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && artifacts.length === 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {[...Array(6)].map((_, i) => (
              <div
                key={i}
                className="h-36 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800 animate-pulse"
              />
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && artifacts.length === 0 && !error && (
          <div className="flex flex-col items-center justify-center py-24 text-center">
            <span className="text-5xl mb-4">📂</span>
            <p className="text-slate-500 dark:text-slate-400 text-sm max-w-xs">
              {t('artifacts.empty')}
            </p>
          </div>
        )}

        {/* Filter + grid */}
        {artifacts.length > 0 && (
          <>
            <FilterBar
              activeKind={activeKind}
              available={available}
              onChange={setActiveKind}
            />
            {visible.length === 0 ? (
              <p className="text-slate-400 text-sm text-center py-12">
                لا توجد ملفات من هذا النوع
              </p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
                {visible.map((a) => (
                  <ArtifactCard
                    key={a.artifact_id}
                    artifact={a}
                    onPreview={setPreview}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </div>

      {/* Preview modal */}
      {preview && (
        <PreviewModal artifact={preview} onClose={() => setPreview(null)} />
      )}
    </AppShell>
  );
}
