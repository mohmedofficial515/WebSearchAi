import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { apiFetch, apiPost } from '@/lib/api';

// ── Types ──────────────────────────────────────────────────────────────────

interface ModelMeta {
  id: string;
  stars?: number;
  speed?: 'fast' | 'medium' | 'slow' | 'local';
  vision?: boolean;
  ctx_k?: number;
}

interface ProviderInfo {
  name: string;
  label: string;
  emoji: string;
  desc: string;
  tier: 'free' | 'paid' | 'local';
  free_info: string;
  signup_url: string;
  key_field: string | null;
  key_placeholder: string;
  model_field: string | null;
  models: ModelMeta[];
  supports_vision: boolean;
  supports_embed: boolean;
  is_configured: boolean;
  key_hint?: string;
  current_model?: string;
}

interface ProvidersResponse {
  active: string;
  providers: ProviderInfo[];
}

interface ProviderTestResponse {
  ok: boolean;
  latency_ms?: number;
  model?: string;
  reply?: string;
  error?: string;
}

type TestStatus = 'idle' | 'testing' | 'ok' | 'fail';

// ── Star renderer ──────────────────────────────────────────────────────────

function Stars({ n }: { n: number }) {
  return (
    <span className="text-amber-400 text-xs" aria-label={`${n} stars`}>
      {'★'.repeat(Math.max(0, Math.min(5, n)))}
      <span className="opacity-30">{'★'.repeat(5 - Math.max(0, Math.min(5, n)))}</span>
    </span>
  );
}

// ── Single provider card ───────────────────────────────────────────────────

interface ProviderCardProps {
  provider: ProviderInfo;
  isActive: boolean;
  onSetActive: (name: string) => void;
  keyValue: string;
  onKeyChange: (val: string) => void;
  modelValue: string;
  onModelChange: (val: string) => void;
}

function ProviderCard({
  provider: p,
  isActive,
  onSetActive,
  keyValue,
  onKeyChange,
  modelValue,
  onModelChange,
}: ProviderCardProps) {
  const { t } = useTranslation();
  const [testStatus, setTestStatus] = useState<TestStatus>('idle');
  const [testMsg, setTestMsg] = useState('');
  const [testReply, setTestReply] = useState('');
  const [liveModels, setLiveModels] = useState<ModelMeta[]>([]);
  const [loadingModels, setLoadingModels] = useState(false);

  const tierLabel = p.tier === 'local' ? 'Local' : p.tier === 'free' ? 'Free' : 'Paid';
  const tierColors =
    p.tier === 'free'
      ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-400'
      : p.tier === 'local'
      ? 'bg-purple-100 text-purple-700 dark:bg-purple-900/30 dark:text-purple-400'
      : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400';

  const selectedModel = liveModels.find((m) => m.id === modelValue) ??
    p.models.find((m) => m.id === modelValue);

  const handleTest = useCallback(async () => {
    setTestStatus('testing');
    setTestMsg(t('providers.testing'));
    setTestReply('');

    // Save current key/model before testing
    const payload: Record<string, string> = {};
    if (keyValue && p.key_field) payload[p.key_field] = keyValue;
    else if (p.name === 'ollama') payload['ollama_base_url'] = keyValue;
    if (modelValue && p.model_field) payload[p.model_field] = modelValue;
    if (Object.keys(payload).length) {
      await apiPost('/api/providers/save', payload).catch(() => {});
    }

    try {
      const data = await apiFetch<ProviderTestResponse>(`/api/providers/test/${p.name}`);
      if (data.ok) {
        const label = data.model ? ` [${data.model}]` : '';
        setTestStatus('ok');
        setTestMsg(`${t('providers.testOk')} · ${data.latency_ms ?? 0}ms${label}`);
        if (data.reply) setTestReply(data.reply);
      } else {
        setTestStatus('fail');
        setTestMsg(`${t('providers.testFail')}: ${data.error ?? ''}`);
      }
    } catch {
      setTestStatus('fail');
      setTestMsg(t('providers.testFail'));
    }
  }, [p, keyValue, modelValue, t]);

  const handleLoadModels = useCallback(async () => {
    if (!p.model_field) return;
    setLoadingModels(true);
    try {
      const data = await apiFetch<{ ok?: boolean; models: ModelMeta[]; source?: string }>(
        `/api/providers/${p.name}/models`,
      );
      if (data.models?.length) setLiveModels(data.models);
    } catch {}
    finally { setLoadingModels(false); }
  }, [p.name, p.model_field]);

  // Load live models when provider is configured
  useEffect(() => {
    if (p.is_configured && p.model_field) handleLoadModels();
  }, [p.is_configured, p.model_field, handleLoadModels]);

  const displayModels = liveModels.length ? liveModels : p.models;

  return (
    <div
      className={`rounded-xl border transition-all ${
        isActive
          ? 'border-indigo-400 dark:border-indigo-600 ring-1 ring-indigo-300 dark:ring-indigo-700'
          : 'border-slate-200 dark:border-slate-700'
      } bg-white dark:bg-slate-900 p-4 space-y-3`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-2xl leading-none">{p.emoji}</span>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-medium text-slate-800 dark:text-slate-200 text-sm">{p.label}</span>
              <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${tierColors}`}>{tierLabel}</span>
              {p.is_configured && (
                <span className="text-xs text-emerald-600 dark:text-emerald-400">● {t('providers.configured')}</span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-0.5 line-clamp-1">{p.desc}</p>
          </div>
        </div>
        <button
          onClick={() => onSetActive(p.name)}
          className={`flex-shrink-0 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors ${
            isActive
              ? 'bg-indigo-600 text-white'
              : 'bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-indigo-50 dark:hover:bg-indigo-950 hover:text-indigo-700 dark:hover:text-indigo-400'
          }`}
        >
          {isActive ? `✓ ${t('providers.active')}` : t('providers.setActive')}
        </button>
      </div>

      {/* Free info + caps */}
      <div className="flex items-center gap-2 flex-wrap">
        <span className="text-xs text-slate-400">🎁 {p.free_info}</span>
        {p.supports_vision && <span className="text-xs bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 px-1.5 py-0.5 rounded">👁 Vision</span>}
        {p.supports_embed && <span className="text-xs bg-violet-50 dark:bg-violet-900/20 text-violet-600 dark:text-violet-400 px-1.5 py-0.5 rounded">📐 Embed</span>}
      </div>

      {/* API key */}
      <div className="flex gap-2">
        <input
          type={p.key_field ? 'password' : 'text'}
          value={keyValue}
          onChange={(e) => onKeyChange(e.target.value)}
          placeholder={p.key_placeholder}
          autoComplete="off"
          className="flex-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-1.5 text-sm text-slate-700 dark:text-slate-300 placeholder:text-slate-400 focus:outline-none focus:ring-1 focus:ring-indigo-400 font-mono"
          dir="ltr"
        />
        <button
          onClick={handleTest}
          disabled={testStatus === 'testing'}
          className="flex-shrink-0 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-indigo-50 dark:hover:bg-indigo-950 hover:text-indigo-700 dark:hover:text-indigo-400 disabled:opacity-50 transition-colors"
        >
          {testStatus === 'testing' ? '⏳' : t('providers.test')}
        </button>
      </div>

      {/* API key link */}
      {p.signup_url && (
        <a
          href={p.signup_url}
          target="_blank"
          rel="noopener noreferrer"
          className="inline-flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 hover:underline"
        >
          → {t('providers.getKey')}: {p.signup_url.replace('https://', '')}
        </a>
      )}

      {/* Model selector */}
      {p.model_field && displayModels.length > 0 && (
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <select
              value={modelValue}
              onChange={(e) => onModelChange(e.target.value)}
              dir="ltr"
              className="flex-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-1.5 text-sm text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-400"
            >
              {displayModels.map((m) => {
                const ctx = m.ctx_k ? ` · ${m.ctx_k}K` : '';
                const vis = m.vision ? ' 👁' : '';
                const spd = m.speed === 'fast' ? ' ⚡' : m.speed === 'slow' ? ' 🐢' : m.speed === 'local' ? ' 💻' : '';
                return (
                  <option key={m.id} value={m.id}>
                    {m.id}{ctx}{vis}{spd}
                  </option>
                );
              })}
            </select>
            {loadingModels && <span className="text-xs text-slate-400">⏳</span>}
          </div>
          {selectedModel && (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              {selectedModel.stars !== undefined && <Stars n={selectedModel.stars} />}
              {selectedModel.vision
                ? <span className="text-blue-500">👁 Vision</span>
                : <span className="text-slate-400">📝 Text only</span>}
              {selectedModel.speed && (
                <span>
                  {selectedModel.speed === 'fast' ? '⚡ Fast' : selectedModel.speed === 'slow' ? '🐢 Slow' : selectedModel.speed === 'local' ? '💻 Local' : '🔄 Medium'}
                </span>
              )}
            </div>
          )}
        </div>
      )}

      {/* Test result */}
      {testMsg && (
        <p
          className={`text-xs ${
            testStatus === 'ok'
              ? 'text-emerald-600 dark:text-emerald-400'
              : testStatus === 'fail'
              ? 'text-rose-600 dark:text-rose-400'
              : 'text-slate-400'
          }`}
        >
          {testMsg}
        </p>
      )}
      {testReply && (
        <pre className="text-xs font-mono text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-800 rounded p-2 overflow-auto max-h-[80px]" dir="ltr">
          {testReply}
        </pre>
      )}
    </div>
  );
}

// ── Main panel ─────────────────────────────────────────────────────────────

export function ProvidersPanel() {
  const { t } = useTranslation();
  const [data, setData] = useState<ProvidersResponse | null>(null);
  const [active, setActive] = useState('auto');
  const [saveStatus, setSaveStatus] = useState<'idle' | 'ok' | 'error'>('idle');

  // Per-provider form state: key input + model selection
  const [keyValues, setKeyValues] = useState<Record<string, string>>({});
  const [modelValues, setModelValues] = useState<Record<string, string>>({});

  const saveTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    apiFetch<ProvidersResponse>('/api/providers')
      .then((res) => {
        setData(res);
        setActive(res.active ?? 'auto');
        const keys: Record<string, string> = {};
        const models: Record<string, string> = {};
        res.providers.forEach((p) => {
          keys[p.name] = p.key_hint ?? '';
          models[p.name] = p.current_model ?? (p.models[0]?.id ?? '');
        });
        setKeyValues(keys);
        setModelValues(models);
      })
      .catch(() => {});
  }, []);

  const handleSave = useCallback(async () => {
    if (!data) return;
    const payload: Record<string, string> = { llm_provider: active };
    data.providers.forEach((p) => {
      const key = keyValues[p.name] ?? '';
      const model = modelValues[p.name] ?? '';
      if (key && p.key_field) payload[p.key_field] = key;
      else if (p.name === 'ollama' && key) payload['ollama_base_url'] = key;
      if (model && p.model_field) payload[p.model_field] = model;
    });
    try {
      await apiPost('/api/providers/save', payload);
      setSaveStatus('ok');
    } catch {
      setSaveStatus('error');
    }
    if (saveTimerRef.current) clearTimeout(saveTimerRef.current);
    saveTimerRef.current = setTimeout(() => setSaveStatus('idle'), 2000);
  }, [data, active, keyValues, modelValues]);

  if (!data) {
    return (
      <div className="py-10 text-center text-sm text-slate-400">
        <span className="animate-pulse">⏳ جارٍ تحميل المزودين...</span>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Active selector bar */}
      <div className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700">
        <label className="text-sm font-medium text-slate-700 dark:text-slate-300 flex-shrink-0">
          {t('providers.title')}:
        </label>
        <select
          value={active}
          onChange={(e) => setActive(e.target.value)}
          dir="ltr"
          className="flex-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 px-3 py-1.5 text-sm text-slate-700 dark:text-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-400"
        >
          <option value="auto">{t('providers.autoProvider')}</option>
          {data.providers.map((p) => (
            <option key={p.name} value={p.name}>{p.emoji} {p.label}</option>
          ))}
        </select>
        <button
          onClick={handleSave}
          className={`flex-shrink-0 px-4 py-1.5 rounded-lg text-sm font-medium transition-colors ${
            saveStatus === 'ok'
              ? 'bg-emerald-600 text-white'
              : saveStatus === 'error'
              ? 'bg-rose-600 text-white'
              : 'bg-indigo-600 text-white hover:bg-indigo-700'
          }`}
        >
          {saveStatus === 'ok' ? t('providers.saveOk') : saveStatus === 'error' ? t('providers.saveError') : t('providers.save')}
        </button>
      </div>

      {/* Provider cards grid */}
      <div className="grid gap-3 sm:grid-cols-2">
        {data.providers.map((p) => (
          <ProviderCard
            key={p.name}
            provider={p}
            isActive={active === p.name}
            onSetActive={(name) => setActive(name)}
            keyValue={keyValues[p.name] ?? ''}
            onKeyChange={(val) => setKeyValues((prev) => ({ ...prev, [p.name]: val }))}
            modelValue={modelValues[p.name] ?? ''}
            onModelChange={(val) => setModelValues((prev) => ({ ...prev, [p.name]: val }))}
          />
        ))}
      </div>
    </div>
  );
}
