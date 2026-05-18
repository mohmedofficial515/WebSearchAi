// Thin bridge: wraps useTaskStream into a stable object consumed by ChatThread.
// We do NOT use @assistant-ui/react's LocalRuntime here — the FastAPI WebSocket
// does not implement the assistant-stream protocol. Instead ChatThread renders
// custom components driven directly by the stream state.
export { useTaskStream } from '@/hooks/useTaskStream';
export type { TaskStreamState, TimelineStep } from '@/hooks/useTaskStream';
