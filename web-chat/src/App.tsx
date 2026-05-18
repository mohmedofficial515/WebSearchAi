import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';

const ChatPage = lazy(() => import('./routes/ChatPage'));
const SettingsPage = lazy(() => import('./routes/SettingsPage'));
const ArtifactsPage = lazy(() => import('./routes/ArtifactsPage'));

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, staleTime: 30_000 } },
});

function PageFallback() {
  return (
    <div className="flex min-h-screen items-center justify-center">
      <span className="text-slate-400 text-sm animate-pulse">⏳</span>
    </div>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/chat">
        <Suspense fallback={<PageFallback />}>
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="/artifacts" element={<ArtifactsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
