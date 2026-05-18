import { useCallback, useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { ChatThread } from '@/components/chat/ChatThread';
import { Composer } from '@/components/chat/Composer';
import { useTaskStream } from '@/hooks/useTaskStream';
import { useTasksStore } from '@/stores/tasksStore';
import type { Message } from '@/lib/types';
import { apiPost } from '@/lib/api';
import type { ChatResponse } from '@/lib/api';
import type { AttachmentEntry } from '@/components/chat/AttachmentPreview';

// Re-export so route imports stay in one place
export type { Message };

let msgCounter = 0;
function newId(): string {
  return `msg-${++msgCounter}-${Date.now()}`;
}

export default function ChatPage() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [activeTaskId, setActiveTaskId] = useState<string | null>(null);
  const [sending, setSending] = useState(false);

  const { tasks, addTask, updateTask } = useTasksStore();

  // Used ONLY for the right drawer — AgentRunCard manages its own stream connection.
  const drawerStream = useTaskStream(activeTaskId);

  const addMsg = useCallback((msg: Message) => setMessages((prev) => [...prev, msg]), []);

  const handleSubmit = useCallback(
    async (text: string, skillOverride: string | null, _attachments?: AttachmentEntry[]) => {
      if (!text || sending) return;

      addMsg({ id: newId(), role: 'user', text, timestamp: Date.now() });
      setSending(true);

      try {
        const body: Record<string, unknown> = { message: text };
        if (skillOverride) body.force_skill = skillOverride;
        // Attach uploaded file URLs so backend can reference them
        const doneAttachments = (_attachments ?? []).filter((a) => a.status === 'done' && a.url);
        if (doneAttachments.length > 0) {
          body.attachments = doneAttachments.map((a) => ({ url: a.url, mime: a.mime }));
        }

        const res = await apiPost<ChatResponse>('/api/chat', body);

        if (res.task_id) {
          const taskId = res.task_id;
          setActiveTaskId(taskId);
          addTask({
            taskId,
            goal: text,
            skill: skillOverride ?? res.intent ?? undefined,
            status: 'running',
            startedAt: Date.now(),
          });
          addMsg({
            id: newId(),
            role: 'assistant',
            text,
            taskId,
            skillHint: skillOverride ?? res.intent ?? undefined,
            timestamp: Date.now(),
          });
        } else if (res.pipeline_id) {
          const pipelineId = res.pipeline_id;
          setActiveTaskId(pipelineId);
          addTask({
            taskId: pipelineId,
            goal: text,
            skill: 'pipeline',
            status: 'running',
            startedAt: Date.now(),
          });
          addMsg({
            id: newId(),
            role: 'assistant',
            text,
            pipelineId,
            pipelineData: res.pipeline ?? null,
            timestamp: Date.now(),
          });
        } else if (res.mode === 'need_params' && res.missing_params) {
          const params = res.missing_params.join('، ');
          addMsg({
            id: newId(),
            role: 'assistant',
            text: `يحتاج الطلب معلومات إضافية: ${params}`,
            timestamp: Date.now(),
          });
        } else {
          addMsg({
            id: newId(),
            role: 'assistant',
            text: 'تم استلام طلبك.',
            timestamp: Date.now(),
          });
        }
      } catch (err) {
        addMsg({
          id: newId(),
          role: 'assistant',
          text: err instanceof Error ? err.message : 'حدث خطأ غير متوقع.',
          timestamp: Date.now(),
        });
      } finally {
        setSending(false);
      }
    },
    [sending, addMsg, addTask],
  );

  const handleSuggestion = useCallback(
    (prompt: string) => void handleSubmit(prompt, null, []),
    [handleSubmit],
  );

  const handleContinue = useCallback(() => {
    // Keep thread active — user continues typing
  }, []);

  const handleEnd = useCallback(() => {
    if (activeTaskId) {
      updateTask(activeTaskId, { status: 'succeeded', completedAt: Date.now() });
    }
    setActiveTaskId(null);
    setMessages([]);
  }, [activeTaskId, updateTask]);

  const handleNewChat = useCallback(() => {
    setActiveTaskId(null);
    setMessages([]);
  }, []);

  const handleSelectTask = useCallback((taskId: string) => {
    setActiveTaskId(taskId);
  }, []);

  return (
    <AppShell
      tasks={tasks}
      activeTaskId={activeTaskId}
      taskStream={drawerStream}
      onNewChat={handleNewChat}
      onSelectTask={handleSelectTask}
    >
      <div className="flex flex-col h-full">
        <div className="flex-1 overflow-y-auto">
          <ChatThread
            messages={messages}
            onChip={(chip) => void handleSubmit(chip, null, [])}
            onSuggestion={handleSuggestion}
            onContinue={handleContinue}
            onEnd={handleEnd}
          />
        </div>
        <Composer
          onSubmit={(txt, s, atts) => void handleSubmit(txt, s, atts)}
          disabled={sending}
        />
      </div>
    </AppShell>
  );
}
