import { useCallback, useEffect, useRef, useState } from 'react';
import { AppShell } from '@/components/layout/AppShell';
import { ChatThread } from '@/components/chat/ChatThread';
import { Composer, type ComposerHandle } from '@/components/chat/Composer';
import { useTaskStream } from '@/hooks/useTaskStream';
import { useTasksStore } from '@/stores/tasksStore';
import { useConversationsStore } from '@/stores/conversationsStore';
import { useSavedDesignsStore } from '@/stores/savedDesignsStore';
import { estimateTokens } from '@/lib/tokens';
import type { Message } from '@/lib/types';
import { apiPost } from '@/lib/api';
import type { ChatResponse } from '@/lib/api';
import type { AttachmentEntry } from '@/components/chat/AttachmentPreview';

export type { Message };

let msgCounter = 0;
function newId(): string {
  return `msg-${++msgCounter}-${Date.now()}`;
}

export default function ChatPage() {
  const { tasks, addTask, updateTask } = useTasksStore();
  const {
    conversations,
    activeId,
    createConversation,
    selectConversation,
    addMessage,
    updateTotalTokens,
    deleteConversation,
  } = useConversationsStore();
  const { addDesign } = useSavedDesignsStore();

  const activeConversation = conversations.find((c) => c.id === activeId);
  const messages = activeConversation?.messages ?? [];
  const totalTokens = activeConversation?.totalTokens ?? 0;

  // Fix 1: use state not ref so Composer disabled prop actually re-renders
  const [sending, setSending] = useState(false);

  // Fix 2: track ONLY tasks started in this session for the right drawer.
  // Deriving activeTaskId from persisted messages causes useTaskStream to
  // reconnect to old tasks whose events are gone from the backend event bus.
  const [liveTaskId, setLiveTaskId] = useState<string | null>(null);

  const composerRef = useRef<ComposerHandle>(null);

  // "/" key focuses Composer
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement).tagName;
      if (e.key === '/' && tag !== 'INPUT' && tag !== 'TEXTAREA' && !e.ctrlKey && !e.metaKey) {
        e.preventDefault();
        composerRef.current?.focus();
      }
    };
    window.addEventListener('keydown', handler);
    return () => window.removeEventListener('keydown', handler);
  }, []);

  // Right drawer watches only the live task (started this session)
  const drawerStream = useTaskStream(liveTaskId);

  // Clear liveTaskId when the task finishes so the drawer closes cleanly
  useEffect(() => {
    if (
      liveTaskId &&
      (drawerStream.status === 'succeeded' ||
        drawerStream.status === 'failed' ||
        drawerStream.status === 'cancelled')
    ) {
      // Give the drawer a moment to show the final state before clearing
      const t = setTimeout(() => setLiveTaskId(null), 800);
      return () => clearTimeout(t);
    }
  }, [liveTaskId, drawerStream.status]);

  // Auto-save html_artifact results to the saved-designs sidebar list.
  useEffect(() => {
    const sr = drawerStream.skillResult;
    if (
      drawerStream.status === 'succeeded' &&
      sr?.skill === 'html_artifact' &&
      liveTaskId &&
      typeof sr.content === 'string' &&
      typeof sr.filename === 'string'
    ) {
      const filename = sr.filename as string;
      // Turn "أنشئ_صفحة_ERP_1748000000" → "أنشئ صفحة ERP"
      const name = filename.replace(/_\d+\.html$/, '').replace(/_/g, ' ').trim();
      addDesign({
        name: name || filename,
        filename,
        content: sr.content as string,
        taskId: liveTaskId,
      });
    }
  }, [drawerStream.status, drawerStream.skillResult, liveTaskId, addDesign]);

  // Fix 3: never create an empty conversation on "New Chat".
  // Only create one when the first message is submitted.
  const handleNewChat = useCallback(() => {
    selectConversation('');   // signal: no active conversation
    setLiveTaskId(null);
  }, [selectConversation]);

  const handleSelectConversation = useCallback(
    (id: string) => {
      selectConversation(id);
      // Fix 2: clear liveTaskId — don't reconnect WS to the old task
      setLiveTaskId(null);
    },
    [selectConversation],
  );

  const handleSelectTask = useCallback(
    (taskId: string) => {
      const conv = conversations.find((c) =>
        c.messages.some((m) => m.taskId === taskId || m.pipelineId === taskId),
      );
      if (conv) selectConversation(conv.id);
    },
    [conversations, selectConversation],
  );

  const handleSubmit = useCallback(
    async (text: string, skillOverride: string | null, _attachments?: AttachmentEntry[]) => {
      if (!text.trim() || sending) return;
      setSending(true);

      // Fix 3: create conversation lazily on first message
      let convId = activeId && activeId !== '' ? activeId : null;
      if (!convId) {
        convId = createConversation();
        selectConversation(convId);
      }

      const userTokens = estimateTokens(text);
      addMessage(convId, {
        id: newId(),
        role: 'user',
        text,
        timestamp: Date.now(),
        tokenCount: userTokens,
      });
      updateTotalTokens(convId, userTokens);

      try {
        const history = messages.slice(-20).map((m) => ({
          role: m.role,
          content: m.text,
        }));

        const body: Record<string, unknown> = {
          message: text,
          conversation_id: convId,
          history,
        };
        if (skillOverride) body.force_skill = skillOverride;
        const doneAttachments = (_attachments ?? []).filter((a) => a.status === 'done' && a.url);
        if (doneAttachments.length > 0) {
          body.attachments = doneAttachments.map((a) => ({ url: a.url, mime: a.mime }));
        }

        const res = await apiPost<ChatResponse>('/api/chat', body);

        if (res.mode === 'chat' && res.reply_text) {
          // Direct LLM reply (no task spawned)
          const replyText = res.reply_text;
          const tok = estimateTokens(replyText);
          addMessage(convId, {
            id: newId(), role: 'assistant', text: replyText, timestamp: Date.now(), tokenCount: tok,
          });
          updateTotalTokens(convId, tok);

        } else if (res.task_id) {
          const taskId = res.task_id;
          // Fix 2: set liveTaskId so ONLY the new session task opens a WS in the drawer
          setLiveTaskId(taskId);
          addTask({
            taskId,
            goal: text,
            skill: skillOverride ?? res.intent ?? undefined,
            status: 'running',
            startedAt: Date.now(),
          });
          const tok = estimateTokens(text);
          addMessage(convId, {
            id: newId(),
            role: 'assistant',
            text,
            taskId,
            skillHint: skillOverride ?? res.intent ?? undefined,
            timestamp: Date.now(),
            tokenCount: tok,
          });
          updateTotalTokens(convId, tok);

        } else if (res.pipeline_id) {
          const pipelineId = res.pipeline_id;
          setLiveTaskId(pipelineId);
          addTask({
            taskId: pipelineId,
            goal: text,
            skill: 'pipeline',
            status: 'running',
            startedAt: Date.now(),
          });
          const tok = estimateTokens(text);
          addMessage(convId, {
            id: newId(),
            role: 'assistant',
            text,
            pipelineId,
            pipelineData: res.pipeline ?? undefined,
            timestamp: Date.now(),
            tokenCount: tok,
          });
          updateTotalTokens(convId, tok);

        } else if (res.mode === 'need_params' && res.missing_params) {
          const replyText = `يحتاج الطلب معلومات إضافية: ${res.missing_params.join('، ')}`;
          const tok = estimateTokens(replyText);
          addMessage(convId, {
            id: newId(), role: 'assistant', text: replyText, timestamp: Date.now(), tokenCount: tok,
          });
          updateTotalTokens(convId, tok);

        } else {
          const replyText = 'تم استلام طلبك.';
          const tok = estimateTokens(replyText);
          addMessage(convId, {
            id: newId(), role: 'assistant', text: replyText, timestamp: Date.now(), tokenCount: tok,
          });
          updateTotalTokens(convId, tok);
        }

      } catch (err) {
        const errText = err instanceof Error ? err.message : 'حدث خطأ غير متوقع.';
        const tok = estimateTokens(errText);
        addMessage(convId, {
          id: newId(), role: 'assistant', text: errText, timestamp: Date.now(), tokenCount: tok,
        });
        updateTotalTokens(convId, tok);
      } finally {
        setSending(false);
      }
    },
    [sending, activeId, createConversation, selectConversation, addMessage, updateTotalTokens, addTask],
  );

  const handleSuggestion = useCallback(
    (prompt: string) => void handleSubmit(prompt, null, []),
    [handleSubmit],
  );

  const handleContinue = useCallback(() => {
    // User chose to continue — keep thread alive
  }, []);

  const handleEnd = useCallback(() => {
    if (liveTaskId) {
      updateTask(liveTaskId, { status: 'succeeded', completedAt: Date.now() });
    }
    setLiveTaskId(null);
  }, [liveTaskId, updateTask]);

  return (
    <AppShell
      tasks={tasks}
      activeTaskId={liveTaskId}
      taskStream={drawerStream}
      onNewChat={handleNewChat}
      onSelectTask={handleSelectTask}
      conversations={conversations}
      activeConversationId={activeId}
      onSelectConversation={handleSelectConversation}
      onDeleteConversation={deleteConversation}
      totalTokens={totalTokens}
    >
      <div className="flex flex-col h-full">
        <div className="flex-1 overflow-y-auto">
          <ChatThread
            messages={messages}
            onChip={(chip) => void handleSubmit(chip, null, [])}
            onSuggestion={handleSuggestion}
            onContinue={handleContinue}
            onEnd={handleEnd}
            thinking={sending}
          />
        </div>
        <Composer
          ref={composerRef}
          onSubmit={(txt, s, atts) => void handleSubmit(txt, s, atts)}
          disabled={sending}
          totalTokens={totalTokens}
        />
      </div>
    </AppShell>
  );
}
