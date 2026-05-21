import { getSkill } from './skills';

export interface SlashCommand {
  command: string;
  skill: string;
  labelAr: string;
  labelEn: string;
  descriptionAr: string;
  descriptionEn: string;
  icon: string;
  category: 'research' | 'web' | 'auth' | 'artifact' | 'transform' | 'misc';
  /** Example goal text appended after the command, hinting at expected input */
  placeholderAr?: string;
  placeholderEn?: string;
}

export const SLASH_COMMANDS: SlashCommand[] = [
  {
    command: '/search', skill: 'research', icon: '🔍', category: 'research',
    labelAr: 'بحث', labelEn: 'Search',
    descriptionAr: 'بحث على الويب وتلخيص المصادر',
    descriptionEn: 'Search the web and summarize sources',
    placeholderAr: 'ما تريد البحث عنه...', placeholderEn: 'what to search for...',
  },
  {
    command: '/explore', skill: 'explore', icon: '🎨', category: 'web',
    labelAr: 'استكشاف موقع', labelEn: 'Explore site',
    descriptionAr: 'تحليل بنية موقع وعناصره البصرية',
    descriptionEn: 'Analyze a site\'s structure and visuals',
    placeholderAr: 'رابط الموقع', placeholderEn: 'site URL',
  },
  {
    command: '/clone', skill: 'clone', icon: '📋', category: 'web',
    labelAr: 'نسخ صفحة', labelEn: 'Clone page',
    descriptionAr: 'نسخ صفحة HTML واحدة بالكامل',
    descriptionEn: 'Clone a single HTML page',
    placeholderAr: 'رابط الصفحة', placeholderEn: 'page URL',
  },
  {
    command: '/site', skill: 'site_clone', icon: '🌐', category: 'web',
    labelAr: 'نسخ موقع كامل', labelEn: 'Clone full site',
    descriptionAr: 'تحميل موقع كامل بالأصول',
    descriptionEn: 'Mirror an entire site with assets',
    placeholderAr: 'رابط الموقع', placeholderEn: 'site URL',
  },
  {
    command: '/components', skill: 'find_components', icon: '🧩', category: 'web',
    labelAr: 'مكوّنات', labelEn: 'Find components',
    descriptionAr: 'البحث عن مكوّنات UI داخل موقع',
    descriptionEn: 'Find UI components inside a site',
    placeholderAr: 'رابط الموقع', placeholderEn: 'site URL',
  },
  {
    command: '/tokens', skill: 'design_tokens', icon: '🎭', category: 'web',
    labelAr: 'رموز تصميم', labelEn: 'Design tokens',
    descriptionAr: 'استخراج الألوان والخطوط من موقع',
    descriptionEn: 'Extract colors and typography',
    placeholderAr: 'رابط الموقع', placeholderEn: 'site URL',
  },
  {
    command: '/login', skill: 'login', icon: '🔐', category: 'auth',
    labelAr: 'دخول', labelEn: 'Login',
    descriptionAr: 'تسجيل دخول إلى موقع باستخدام حساب موجود',
    descriptionEn: 'Sign in to a site with an existing account',
  },
  {
    command: '/signup', skill: 'signup', icon: '📝', category: 'auth',
    labelAr: 'اشتراك', labelEn: 'Sign up',
    descriptionAr: 'إنشاء حساب جديد في موقع',
    descriptionEn: 'Create a new account on a site',
  },
  {
    command: '/temp', skill: 'temp_signup', icon: '🕐', category: 'auth',
    labelAr: 'حساب مؤقت', labelEn: 'Temp account',
    descriptionAr: 'إنشاء حساب مؤقت ببريد متاح للاستخدام',
    descriptionEn: 'Create a throwaway account with disposable email',
  },
  {
    command: '/md', skill: 'md_writer', icon: '📄', category: 'artifact',
    labelAr: 'تقرير Markdown', labelEn: 'Markdown report',
    descriptionAr: 'كتابة تقرير منسّق بصيغة Markdown',
    descriptionEn: 'Write a structured Markdown document',
    placeholderAr: 'موضوع التقرير', placeholderEn: 'report topic',
  },
  {
    command: '/html', skill: 'html_artifact', icon: '🌐', category: 'artifact',
    labelAr: 'صفحة HTML', labelEn: 'HTML page',
    descriptionAr: 'إنشاء صفحة HTML قابلة للعرض',
    descriptionEn: 'Generate a renderable HTML page',
    placeholderAr: 'وصف الصفحة', placeholderEn: 'page description',
  },
  {
    command: '/code', skill: 'code_artifact', icon: '💻', category: 'artifact',
    labelAr: 'كود برمجي', labelEn: 'Code snippet',
    descriptionAr: 'إنتاج مقطع كود في أي لغة',
    descriptionEn: 'Produce a code snippet in any language',
    placeholderAr: 'ما تريد برمجته', placeholderEn: 'what to build',
  },
  {
    command: '/diagram', skill: 'mermaid_diagram', icon: '📊', category: 'artifact',
    labelAr: 'مخطط', labelEn: 'Diagram',
    descriptionAr: 'مخطط Mermaid (تدفّق، تسلسل، علاقات)',
    descriptionEn: 'Mermaid diagram (flow, sequence, ER)',
    placeholderAr: 'وصف المخطط', placeholderEn: 'diagram description',
  },
  {
    command: '/pdf', skill: 'pdf_export', icon: '📑', category: 'artifact',
    labelAr: 'تصدير PDF', labelEn: 'Export PDF',
    descriptionAr: 'تحويل آخر مخرَج إلى PDF',
    descriptionEn: 'Convert latest output to PDF',
  },
  {
    command: '/summary', skill: 'summarize', icon: '📰', category: 'transform',
    labelAr: 'تلخيص', labelEn: 'Summarize',
    descriptionAr: 'تلخيص نص أو مصدر',
    descriptionEn: 'Summarize text or a source',
    placeholderAr: 'النص أو الرابط', placeholderEn: 'text or URL',
  },
  {
    command: '/translate', skill: 'translate', icon: '🌍', category: 'transform',
    labelAr: 'ترجمة', labelEn: 'Translate',
    descriptionAr: 'ترجمة نص بين اللغات',
    descriptionEn: 'Translate text between languages',
    placeholderAr: 'النص المراد ترجمته', placeholderEn: 'text to translate',
  },
  {
    command: '/compare', skill: 'competitor_matrix', icon: '📈', category: 'research',
    labelAr: 'مقارنة منافسين', labelEn: 'Competitor matrix',
    descriptionAr: 'جدول مقارنة بين منتجات أو شركات',
    descriptionEn: 'Comparison table of products/companies',
    placeholderAr: 'المنافسون', placeholderEn: 'competitors to compare',
  },
  {
    command: '/run', skill: 'run', icon: '🤖', category: 'misc',
    labelAr: 'تشغيل وكيل عام', labelEn: 'Generic agent',
    descriptionAr: 'تشغيل وكيل عام يقرّر الأداة تلقائياً',
    descriptionEn: 'Run a generic agent — it picks the tool',
  },
];

// Quick lookup
const COMMAND_BY_NAME: Record<string, SlashCommand> = Object.fromEntries(
  SLASH_COMMANDS.map((c) => [c.command, c]),
);

export function getCommand(name: string): SlashCommand | null {
  return COMMAND_BY_NAME[name.toLowerCase()] ?? null;
}

/**
 * Return the skill id when the input begins with a registered slash command.
 * Matches both exact (`/search`) and prefixed (`/search foo`) forms.
 */
export function parseSlashCommand(text: string): string | null {
  const lower = text.trim().toLowerCase();
  if (!lower.startsWith('/')) return null;
  const match = SLASH_COMMANDS.find(
    (c) => lower === c.command || lower.startsWith(c.command + ' '),
  );
  return match?.skill ?? null;
}

/**
 * Suggestions for the slash-command dropdown.
 *
 * - When `text` is just `/`, return everything (sorted by category then label).
 * - When `text` is `/foo`, fuzzy-match against command, label, description.
 * - When `text` doesn't start with `/`, return [].
 *
 * The first item is always the best match; the dropdown uses index 0 as the
 * default selection.
 */
export function getSuggestedCommands(text: string): SlashCommand[] {
  if (!text.startsWith('/')) return [];
  const query = text.slice(1).toLowerCase().trim();

  if (query.length === 0) {
    // Show everything, grouped by category
    return [...SLASH_COMMANDS].sort((a, b) => {
      if (a.category !== b.category) {
        return CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category);
      }
      return 0;
    });
  }

  // Score and sort
  const scored = SLASH_COMMANDS.map((c) => ({ cmd: c, score: scoreMatch(c, query) }))
    .filter((s) => s.score > 0)
    .sort((a, b) => b.score - a.score);

  return scored.map((s) => s.cmd);
}

const CATEGORY_ORDER: SlashCommand['category'][] = [
  'research', 'web', 'auth', 'artifact', 'transform', 'misc',
];

function scoreMatch(cmd: SlashCommand, query: string): number {
  const name = cmd.command.slice(1).toLowerCase();
  const ar = cmd.labelAr;
  const en = cmd.labelEn.toLowerCase();
  const descAr = cmd.descriptionAr;
  const descEn = cmd.descriptionEn.toLowerCase();

  // Exact command match wins
  if (name === query) return 100;
  // Prefix on command name is very strong
  if (name.startsWith(query)) return 80;
  // Substring on command name
  if (name.includes(query)) return 60;
  // Prefix on English label
  if (en.startsWith(query)) return 50;
  // Substring on Arabic label (use raw)
  if (ar.includes(query)) return 45;
  // Substring on English label
  if (en.includes(query)) return 40;
  // Description match (Arabic or English)
  if (descAr.includes(query) || descEn.includes(query)) return 20;
  return 0;
}

/** SkillMeta for a command — falls back to the generic 'run' skill. */
export function commandSkillMeta(cmd: SlashCommand) {
  return getSkill(cmd.skill);
}
