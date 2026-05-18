import { useState } from 'react';
import { apiPost } from '@/lib/api';
import type { RequiredField } from '@/lib/events';

interface PipelinePausedFormProps {
  pipelineId: string;
  stepId: string;
  fields: RequiredField[];
  onResumed: () => void;
}

export function PipelinePausedForm({ pipelineId, stepId, fields, onResumed }: PipelinePausedFormProps) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const set = (name: string, value: string) =>
    setValues((prev) => ({ ...prev, [name]: value }));

  const submit = async () => {
    // Validate required fields
    const missing = fields.filter((f) => f.required && !values[f.name]?.trim());
    if (missing.length > 0) {
      setError(`الحقول المطلوبة: ${missing.map((f) => f.label_ar).join('، ')}`);
      return;
    }

    setLoading(true);
    setError(null);
    try {
      await apiPost(`/api/pipelines/${pipelineId}/resume`, {
        step_inputs: { [stepId]: values },
      });
      onResumed();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'فشل استئناف الخطة');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="px-5 py-4 border-t border-amber-100 dark:border-amber-900/30 bg-amber-50 dark:bg-amber-900/10">
      <div className="flex items-center gap-2 mb-3">
        <span>⏸</span>
        <p className="text-sm font-medium text-amber-800 dark:text-amber-300">
          يحتاج الخطوة التالية لمعلومات إضافية
        </p>
      </div>

      <div className="space-y-3">
        {fields.map((field) => (
          <div key={field.name} className="flex flex-col gap-1">
            <label className="text-xs font-medium text-slate-600 dark:text-slate-400">
              {field.label_ar}
              {field.required && <span className="text-rose-500 mr-0.5">*</span>}
            </label>
            <input
              type={field.type === 'password' ? 'password' : field.type === 'email' ? 'email' : 'text'}
              value={values[field.name] ?? ''}
              onChange={(e) => set(field.name, e.target.value)}
              placeholder={field.label_ar}
              className="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900 text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        ))}
      </div>

      {error && <p className="text-xs text-rose-500 mt-2">{error}</p>}

      <button
        onClick={() => void submit()}
        disabled={loading}
        className="mt-3 flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium transition-colors"
      >
        {loading ? <span className="animate-spin">⏳</span> : <span>▶</span>}
        متابعة
      </button>
    </div>
  );
}
