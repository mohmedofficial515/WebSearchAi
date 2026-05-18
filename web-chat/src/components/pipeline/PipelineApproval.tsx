import { useState } from 'react';
import { apiPost } from '@/lib/api';

interface PipelineApprovalProps {
  pipelineId: string;
  onApproved: () => void;
  onCancelled: () => void;
}

export function PipelineApproval({ pipelineId, onApproved, onCancelled }: PipelineApprovalProps) {
  const [loading, setLoading] = useState<'approve' | 'cancel' | null>(null);
  const [error, setError] = useState<string | null>(null);

  const approve = async () => {
    setLoading('approve');
    setError(null);
    try {
      await apiPost(`/api/pipelines/${pipelineId}/approve`);
      onApproved();
    } catch (e) {
      setError(e instanceof Error ? e.message : 'فشل بدء الخطة');
    } finally {
      setLoading(null);
    }
  };

  const cancel = async () => {
    setLoading('cancel');
    setError(null);
    try {
      await apiPost(`/api/pipelines/${pipelineId}/cancel`);
      onCancelled();
    } catch {
      // ignore cancel errors — UI clears regardless
      onCancelled();
    } finally {
      setLoading(null);
    }
  };

  return (
    <div className="px-5 py-4 border-t border-slate-100 dark:border-slate-800">
      {error && <p className="text-xs text-rose-500 mb-2">{error}</p>}
      <div className="flex items-center gap-2">
        <button
          onClick={() => void approve()}
          disabled={loading !== null}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white text-sm font-medium transition-colors"
        >
          {loading === 'approve' ? (
            <span className="animate-spin">⏳</span>
          ) : (
            <span>▶</span>
          )}
          تشغيل
        </button>

        <button
          onClick={() => void cancel()}
          disabled={loading !== null}
          className="flex items-center gap-1.5 px-4 py-2 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-50 text-slate-700 dark:text-slate-300 text-sm font-medium transition-colors"
        >
          {loading === 'cancel' ? (
            <span className="animate-spin">⏳</span>
          ) : (
            <span>✕</span>
          )}
          إلغاء
        </button>
      </div>
    </div>
  );
}
