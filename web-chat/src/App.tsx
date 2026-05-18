import { BrowserRouter, Routes, Route, Navigate, useLocation } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { lazy, Suspense } from 'react';
import { AnimatePresence, motion } from 'framer-motion';

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

function AppRoutes() {
  const location = useLocation();
  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={location.pathname}
        className="h-full"
        initial={{ opacity: 0, y: 6 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -6 }}
        transition={{ duration: 0.18, ease: 'easeOut' }}
      >
        <Routes location={location}>
          <Route path="/" element={<ChatPage />} />
          <Route path="/settings" element={<SettingsPage />} />
          <Route path="/artifacts" element={<ArtifactsPage />} />
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </motion.div>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter basename="/chat">
        <Suspense fallback={<PageFallback />}>
          <AppRoutes />
        </Suspense>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
