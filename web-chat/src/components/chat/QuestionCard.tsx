import { useState } from 'react';
import type { AgentQuestion, QuestionOption } from '@/lib/events';

interface QuestionCardProps {
  taskId: string;
  question: AgentQuestion;
  onAnswered: () => void;
}

async function submitAnswer(taskId: string, questionId: string, value: unknown): Promise<void> {
  await fetch(`/api/tasks/${taskId}/answer`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ question_id: questionId, value }),
  });
}

function SingleSelect({
  options,
  selected,
  onSelect,
}: {
  options: QuestionOption[];
  selected: string;
  onSelect: (v: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {options.map((opt) => (
        <button
          key={opt.value}
          onClick={() => onSelect(opt.value)}
          className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl border-2 text-sm transition-all text-start ${
            selected === opt.value
              ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 font-medium'
              : 'border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 text-slate-700 dark:text-slate-300'
          }`}
        >
          {opt.icon && <span className="text-lg leading-none flex-shrink-0">{opt.icon}</span>}
          <span className="leading-tight">{opt.label}</span>
          {selected === opt.value && (
            <span className="ms-auto text-indigo-500 text-xs">✓</span>
          )}
        </button>
      ))}
    </div>
  );
}

function MultiSelect({
  options,
  selected,
  onToggle,
}: {
  options: QuestionOption[];
  selected: string[];
  onToggle: (v: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {options.map((opt) => {
        const isOn = selected.includes(opt.value);
        return (
          <button
            key={opt.value}
            onClick={() => onToggle(opt.value)}
            className={`flex items-center gap-2.5 px-3 py-2.5 rounded-xl border-2 text-sm transition-all text-start ${
              isOn
                ? 'border-indigo-500 bg-indigo-50 dark:bg-indigo-950/40 text-indigo-700 dark:text-indigo-300 font-medium'
                : 'border-slate-200 dark:border-slate-700 hover:border-indigo-300 dark:hover:border-indigo-700 text-slate-700 dark:text-slate-300'
            }`}
          >
            <span className={`w-4 h-4 rounded flex-shrink-0 border-2 flex items-center justify-center text-[10px] ${
              isOn ? 'border-indigo-500 bg-indigo-500 text-white' : 'border-slate-300 dark:border-slate-600'
            }`}>
              {isOn && '✓'}
            </span>
            {opt.icon && <span className="text-base leading-none flex-shrink-0">{opt.icon}</span>}
            <span className="leading-tight">{opt.label}</span>
          </button>
        );
      })}
    </div>
  );
}

function SliderInput({
  range,
  value,
  onChange,
}: {
  range: NonNullable<AgentQuestion['range']>;
  value: number;
  onChange: (v: number) => void;
}) {
  return (
    <div className="space-y-2">
      <input
        type="range"
        min={range.min}
        max={range.max}
        step={range.step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full accent-indigo-600"
      />
      <div className="flex justify-between text-xs text-slate-400">
        <span>{range.min}</span>
        <span className="font-medium text-indigo-600 dark:text-indigo-400">{value}</span>
        <span>{range.max}</span>
      </div>
    </div>
  );
}

export function QuestionCard({ taskId, question, onAnswered }: QuestionCardProps) {
  const [singleVal, setSingleVal] = useState('');
  const [multiVal, setMultiVal] = useState<string[]>([]);
  const [sliderVal, setSliderVal] = useState(question.range?.defaultValue ?? question.range?.min ?? 0);
  const [textVal, setTextVal] = useState('');
  const [submitting, setSubmitting] = useState(false);

  const toggleMulti = (v: string) =>
    setMultiVal((prev) => (prev.includes(v) ? prev.filter((x) => x !== v) : [...prev, v]));

  const canSubmit = (() => {
    if (submitting) return false;
    if (question.field_type === 'single') return singleVal !== '';
    if (question.field_type === 'multi') return multiVal.length > 0;
    if (question.field_type === 'text') return textVal.trim() !== '';
    return true; // slider always has a value
  })();

  const handleSubmit = async () => {
    if (!canSubmit) return;
    setSubmitting(true);
    let value: unknown;
    if (question.field_type === 'single') value = singleVal;
    else if (question.field_type === 'multi') value = multiVal;
    else if (question.field_type === 'slider') value = sliderVal;
    else value = textVal.trim();

    try {
      await submitAnswer(taskId, question.question_id, value);
      onAnswered();
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="rounded-2xl border-2 border-indigo-200 dark:border-indigo-800 bg-white dark:bg-slate-900 shadow-md overflow-hidden">
      {/* Header */}
      <div className="px-5 py-3 bg-gradient-to-l from-indigo-50 to-transparent dark:from-indigo-950/30 border-b border-indigo-100 dark:border-indigo-900/40 flex items-center gap-3">
        <span className="text-xl">🤔</span>
        <div>
          <p className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 uppercase tracking-wider">وكيل التصميم يسألك</p>
          <p className="text-sm font-medium text-slate-800 dark:text-slate-200 mt-0.5">{question.question}</p>
        </div>
      </div>

      {/* Options */}
      <div className="px-5 py-4">
        {question.field_type === 'single' && question.options && (
          <SingleSelect options={question.options} selected={singleVal} onSelect={setSingleVal} />
        )}
        {question.field_type === 'multi' && question.options && (
          <MultiSelect options={question.options} selected={multiVal} onToggle={toggleMulti} />
        )}
        {question.field_type === 'slider' && question.range && (
          <SliderInput range={question.range} value={sliderVal} onChange={setSliderVal} />
        )}
        {question.field_type === 'text' && (
          <textarea
            value={textVal}
            onChange={(e) => setTextVal(e.target.value)}
            rows={3}
            placeholder="اكتب إجابتك هنا..."
            className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 px-3 py-2 text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-indigo-300 dark:focus:ring-indigo-700 resize-none"
            dir="auto"
          />
        )}
      </div>

      {/* Submit */}
      <div className="px-5 py-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
        {question.field_type === 'multi' && (
          <span className="text-xs text-slate-400">{multiVal.length} مختار</span>
        )}
        <div className="ms-auto">
          <button
            onClick={() => void handleSubmit()}
            disabled={!canSubmit}
            className="px-5 py-2 rounded-xl bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            {submitting ? 'جارٍ الإرسال...' : 'تأكيد ←'}
          </button>
        </div>
      </div>
    </div>
  );
}
