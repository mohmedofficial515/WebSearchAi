interface LiveScreenshotProps {
  screenshot: string | null;
  status: string;
}

export function LiveScreenshot({ screenshot, status }: LiveScreenshotProps) {
  if (!screenshot) {
    return (
      <div className="aspect-video rounded-xl bg-slate-100 dark:bg-slate-800 flex items-center justify-center">
        <span className="text-slate-400 text-sm">
          {status === 'connecting' ? '⏳ جارٍ الاتصال...' : '📷 لا توجد لقطة بعد'}
        </span>
      </div>
    );
  }

  return (
    <img
      src={`data:image/png;base64,${screenshot}`}
      alt="لقطة الشاشة الحية"
      className="w-full rounded-xl border border-slate-100 dark:border-slate-700 aspect-video object-cover object-top"
    />
  );
}
