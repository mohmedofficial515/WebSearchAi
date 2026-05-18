import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiFetch } from '@/lib/api';

// ── Types ──────────────────────────────────────────────────────────────────

interface ArchiveItem {
  task_id: string;
  goal: string;
  summary: string;
  score: number | null;
  matched_terms: string[];
  created_at: number | null;
}

interface ArchiveDetail {
  task_id: string;
  goal: string;
  summary: string;
  confidence: number | null;
  success: boolean;
  created_at: number | null;
  extractions: unknown[];
  plan: unknown;
  result: unknown;
}

interface SearchResponse {
  matches: ArchiveItem[];
}

// ── Detail modal ───────────────────────────────────────────────────────────

interface DetailModalProps {
  taskId: string;
  onClose: () => void;
  onReplay: (goal: string) => void;
  onDelete: (taskId: string) => void;
}

function DetailModal({ taskId, onClose, onReplay, onDelete }: DetailModalProps) {
  const { t } = useTranslation();
  const [detail, setDetail] = useState<ArchiveDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    apiFetch<ArchiveDetail>(`/api/archive/${encodeURIComponent(taskId)}`)
      .then(setDetail)
      .catch((e) => setError(String((e as Error).message ?? e)))
      .finally(() => setLoading(false));
  }, [taskId]);

  const handleDelete = useCallback(async () => {
    if (!window.confirm(t('archive.confirmDelete'))) return;
    await apiFetch(`/api/archive/${encodeURIComponent(taskId)}`, { method: 'DELETE' }).catch(() => {});
    onDelete(taskId);
    onClose();
  }, [taskId, t, onDelete, onClose]);

  const conf = detail?.confidence != null
    ? (detail.confidence * 100).toFixed(0) + '%'
    : '—';
  const date = detail?.created_at
    ? new Date(detail.created_at * 1000).toLocaleString()
    : '';

  return (
    <div
      ref={overlayRef}
      onClick={(e) => { if (e.target === overlayRef.current) onClose(); }}
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 backdrop-blur-sm p-4"
    >
      <div
        className="w-full max-w-2xl max-h-[85vh] overflow-y-auto rounded-2xl bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 shadow-2xl"
        dir="rtl"
      >
        {/* Modal header */}
        <div className="sticky top-0 flex items-center justify-between px-5 py-3 border-b border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 z-10">
          <span className="text-sm font-medium text-slate-600 dark:text-slate-400 font-mono" dir="ltr">
            {taskId}
          </span>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 text-lg leading-none"
          >
            ✕
          </button>
        </div>

        <div className="p-5 space-y-4">
          {loading && <p className="text-sm text-slate-400 animate-pulse">{t('archive.loading')}</p>}
          {error && <p className="text-sm text-rose-600 dark:text-rose-400">{t('archive.loadError')}: {error}</p>}

          {detail && (
            <>
              {/* Meta row */}
              <div className="flex items-center gap-3 flex-wrap text-xs">
                <span className={detail.success ? 'text-emerald-600 dark:text-emerald-400' : 'text-rose-600 dark:text-rose-400'}>
                  {detail.success ? t('archive.success') : t('archive.fail')}
                </span>
                <span className="text-slate-400">{t('archive.confidence')}: {conf}</span>
                {date && <span className="text-slate-400">{date}</span>}
              </div>

              {/* Goal */}
              <section>
                <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">{t('archive.goal')}</h4>
                <p className="text-sm text-slate-800 dark:text-slate-200">{detail.goal || '—'}</p>
              </section>

              {/* Summary */}
              {detail.summary && (
                <section>
                  <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">{t('archive.summary')}</h4>
                  <p className="text-sm text-slate-600 dark:text-slate-400 whitespace-pre-wrap">{detail.summary}</p>
                </section>
              )}

              {/* Extractions */}
              {Array.isArray(detail.extractions) && detail.extractions.length > 0 && (
                <section>
                  <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">{t('archive.extractions')}</h4>
                  <div className="space-y-1 max-h-[150px] overflow-auto">
                    {detail.extractions.slice(0, 5).map((ex, i) => (
                      <pre
                        key={i}
                        className="text-xs font-mono text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 rounded p-2 overflow-auto"
                        dir="ltr"
                      >
                        {String(ex).slice(0, 1500)}
                      </pre>
                    ))}
                  </div>
                </section>
              )}

              {/* Plan */}
              {detail.plan && (
                <section>
                  <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">{t('archive.plan')}</h4>
                  <pre className="text-xs font-mono text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 rounded p-2 overflow-auto max-h-[120px]" dir="ltr">
                    {JSON.stringify(detail.plan, null, 2)}
                  </pre>
                </section>
              )}

              {/* Full result */}
              {detail.result && (
                <section>
                  <h4 className="text-xs font-medium text-slate-500 uppercase tracking-wide mb-1">{t('archive.result')}</h4>
                  <pre className="text-xs font-mono text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 rounded p-2 overflow-auto max-h-[120px]" dir="ltr">
                    {JSON.stringify(detail.result, null, 2)}
                  </pre>
                </section>
              )}

              {/* Actions */}
              <div className="flex items-center gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                <button
                  onClick={() => { onReplay(detail.goal || ''); onClose(); }}
                  className="px-4 py-2 rounded-lg text-sm font-medium bg-indigo-600 text-white hover:bg-indigo-700 transition-colors"
                >
                  {t('archive.replay')}
                </button>
                <button
                  onClick={handleDelete}
                  className="px-4 py-2 rounded-lg text-sm text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-900/20 transition-colors"
                >
                  {t('archive.delete')}
                </button>
                <button
                  onClick={onClose}
                  className="ms-auto px-4 py-2 rounded-lg text-sm text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                >
                  {t('archive.close')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

// ── Main component ─────────────────────────────────────────────────────────

interface ArchiveBrowserProps {
  onReplay?: (goal: string) => void;
}

export function ArchiveBrowser({ onReplay }: ArchiveBrowserProps) {
  const { t } = useTranslation();
  const [items, setItems] = useState<ArchiveItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [query, setQuery] = useState('');
  const [openTaskId, setOpenTaskId] = useState<string | null>(null);
  const searchTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const loadAll = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const raw = await apiFetch<ArchiveItem[]>('/api/archive?limit=50');
      setItems(raw.map((it) => ({ ...it, score: null, matched_terms: [] })));
    } catch (e) {
      setError(t('archive.loadError') + ': ' + String((e as Error).message ?? e));
    } finally {
      setLoading(false);
    }
  }, [t]);

  const doSearch = useCallback(async (q: string) => {
    if (!q.trim()) { loadAll(); return; }
    setLoading(true);
    setError('');
    try {
      const data = await apiFetch<SearchResponse>(`/api/archive/search?q=${encodeURIComponent(q)}`);
      setItems(data.matches ?? []);
    } catch (e) {
      setError(t('archive.loadError') + ': ' + String((e as Error).message ?? e));
    } finally {
      setLoading(false);
    }
  }, [loadAll, t]);

  useEffect(() => { loadAll(); }, [loadAll]);

  const handleQueryChange = (q: string) => {
    setQuery(q);
    if (searchTimer.current) clearTimeout(searchTimer.current);
    searchTimer.current = setTimeout(() => doSearch(q), 350);
  };

  const handleDelete = useCallback((taskId: string) => {
    setItems((prev) => prev.filter((it) => it.task_id !== taskId));
  }, []);

  return (
    <div className="space-y-4">
      {/* Header + search */}
      <div className="flex items-center gap-3">
        <input
          type="search"
          value={query}
          onChange={(e) => handleQueryChange(e.target.value)}
          placeholder={t('archive.search')}
          className="flex-1 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-4 py-2 text-sm text-slate-700 dark:text-slate-300 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-400"
          dir="rtl"
        />
        <button
          onClick={() => doSearch(query)}
          disabled={loading}
          className="flex-shrink-0 px-3 py-2 rounded-xl text-sm bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 transition-colors"
        >
          {loading ? '⏳' : '🔍'}
        </button>
      </div>

      {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}

      {!loading && items.length === 0 && !error && (
        <p className="text-sm text-slate-400">{query ? t('archive.searchEmpty') : t('archive.empty')}</p>
      )}

      {/* List */}
      <ul className="space-y-2">
        {items.map((it) => {
          const date = it.created_at ? new Date(it.created_at * 1000).toLocaleString() : '';
          const score = typeof it.score === 'number' ? Math.round(it.score * 100) : null;
          return (
            <li
              key={it.task_id}
              onClick={() => setOpenTaskId(it.task_id)}
              className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4 cursor-pointer hover:border-indigo-300 dark:hover:border-indigo-700 hover:shadow-sm transition-all"
              dir="rtl"
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <span className="text-xs text-slate-400">{date}</span>
                {score !== null && (
                  <span className="text-xs font-medium text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-900/20 px-1.5 py-0.5 rounded">
                    {score}%
                  </span>
                )}
              </div>
              <p className="text-sm font-medium text-slate-800 dark:text-slate-200 line-clamp-2">{it.goal || '—'}</p>
              {it.summary && (
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-1 line-clamp-2">{it.summary}</p>
              )}
              {it.matched_terms.length > 0 && (
                <div className="flex flex-wrap gap-1 mt-2">
                  {it.matched_terms.map((term) => (
                    <span key={term} className="text-xs px-1.5 py-0.5 rounded bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400">
                      {term}
                    </span>
                  ))}
                </div>
              )}
            </li>
          );
        })}
      </ul>

      {/* Detail modal */}
      {openTaskId && (
        <DetailModal
          taskId={openTaskId}
          onClose={() => setOpenTaskId(null)}
          onReplay={(goal) => { onReplay?.(goal); }}
          onDelete={handleDelete}
        />
      )}
    </div>
  );
}
