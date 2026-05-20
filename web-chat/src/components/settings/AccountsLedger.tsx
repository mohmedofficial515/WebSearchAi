import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { RotateCw, Trash2, Check, Minus } from 'lucide-react';
import { apiFetch } from '@/lib/api';

interface Account {
  profile_name: string;
  verified: boolean;
  site_url: string;
  email: string;
}

export function AccountsLedger() {
  const { t } = useTranslation();
  const [accounts, setAccounts] = useState<Account[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const items = await apiFetch<Account[]>('/api/accounts');
      setAccounts(items);
    } catch (e) {
      setError(t('accounts.loadError') + ': ' + String((e as Error).message ?? e));
    } finally {
      setLoading(false);
    }
  }, [t]);

  useEffect(() => { load(); }, [load]);

  const handleDelete = useCallback(async (slug: string) => {
    if (!window.confirm(t('accounts.confirmDelete'))) return;
    try {
      await apiFetch(`/api/accounts/${encodeURIComponent(slug)}`, { method: 'DELETE' });
      setAccounts((prev) => prev.filter((a) => a.profile_name !== slug));
    } catch {}
  }, [t]);

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h2 className="text-base font-medium text-slate-800 dark:text-slate-200">
          {t('accounts.title')}
        </h2>
        <button
          onClick={load}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 transition-colors"
        >
          <RotateCw className={`h-3 w-3 ${loading ? 'animate-spin' : ''}`} />
          {t('accounts.refresh')}
        </button>
      </div>

      {loading && (
        <p className="text-sm text-slate-400 animate-pulse">{t('accounts.loading')}</p>
      )}

      {error && (
        <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>
      )}

      {!loading && !error && accounts.length === 0 && (
        <p className="text-sm text-slate-400">{t('accounts.empty')}</p>
      )}

      {!loading && accounts.length > 0 && (
        <ul className="space-y-2">
          {accounts.map((a) => (
            <li
              key={a.profile_name}
              className="rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 p-4"
              dir="rtl"
            >
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="font-medium text-slate-800 dark:text-slate-200 text-sm">
                      {a.profile_name || '?'}
                    </span>
                    <span
                      className={`inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded font-medium ${
                        a.verified
                          ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
                          : 'bg-slate-100 text-slate-500 dark:bg-slate-800 dark:text-slate-400'
                      }`}
                    >
                      {a.verified ? <Check className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
                      {a.verified ? t('accounts.verified') : t('accounts.unverified')}
                    </span>
                  </div>
                  {a.site_url && (
                    <p className="text-xs text-slate-400 truncate">{a.site_url}</p>
                  )}
                  {a.email && (
                    <p className="text-xs font-mono text-slate-500 dark:text-slate-400" dir="ltr">
                      {a.email}
                    </p>
                  )}
                </div>
                <button
                  onClick={() => handleDelete(a.profile_name)}
                  className="flex-shrink-0 inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-900/20 transition-colors"
                >
                  <Trash2 className="h-3 w-3" />
                  {t('accounts.delete')}
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
