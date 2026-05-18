export interface SkillMeta {
  id: string;
  labelAr: string;
  labelEn: string;
  icon: string;
  color: string;
}

export const SKILLS: SkillMeta[] = [
  { id: 'research',          labelAr: 'بحث',           labelEn: 'Research',        icon: '🔍', color: 'bg-blue-100 text-blue-800'    },
  { id: 'explore',           labelAr: 'استكشاف',       labelEn: 'Explore',         icon: '🎨', color: 'bg-purple-100 text-purple-800' },
  { id: 'clone',             labelAr: 'نسخ صفحة',     labelEn: 'Clone Page',      icon: '📋', color: 'bg-green-100 text-green-800'  },
  { id: 'site_clone',        labelAr: 'نسخ موقع',     labelEn: 'Clone Site',      icon: '🌐', color: 'bg-teal-100 text-teal-800'    },
  { id: 'components',        labelAr: 'مكوّنات',       labelEn: 'Components',      icon: '🧩', color: 'bg-orange-100 text-orange-800' },
  { id: 'design_tokens',     labelAr: 'رموز تصميم',   labelEn: 'Design Tokens',   icon: '🎭', color: 'bg-pink-100 text-pink-800'    },
  { id: 'login',             labelAr: 'دخول',          labelEn: 'Login',           icon: '🔐', color: 'bg-red-100 text-red-800'      },
  { id: 'signup',            labelAr: 'اشتراك',        labelEn: 'Sign Up',         icon: '📝', color: 'bg-cyan-100 text-cyan-800'    },
  { id: 'temp_signup',       labelAr: 'حساب مؤقت',    labelEn: 'Temp Account',    icon: '🕐', color: 'bg-amber-100 text-amber-800'  },
  { id: 'md_writer',         labelAr: 'تقرير MD',     labelEn: 'MD Report',       icon: '📄', color: 'bg-slate-100 text-slate-700'  },
  { id: 'html_artifact',     labelAr: 'صفحة HTML',    labelEn: 'HTML Page',       icon: '🌐', color: 'bg-lime-100 text-lime-800'    },
  { id: 'code_artifact',     labelAr: 'كود',           labelEn: 'Code',            icon: '💻', color: 'bg-gray-100 text-gray-700'    },
  { id: 'mermaid_diagram',   labelAr: 'مخطط',          labelEn: 'Diagram',         icon: '📊', color: 'bg-violet-100 text-violet-800' },
  { id: 'pdf_export',        labelAr: 'PDF',            labelEn: 'Export PDF',      icon: '📑', color: 'bg-rose-100 text-rose-800'    },
  { id: 'summarize',         labelAr: 'تلخيص',         labelEn: 'Summarize',       icon: '📰', color: 'bg-sky-100 text-sky-800'      },
  { id: 'translate',         labelAr: 'ترجمة',          labelEn: 'Translate',       icon: '🌍', color: 'bg-emerald-100 text-emerald-800' },
  { id: 'competitor_matrix', labelAr: 'مقارنة',        labelEn: 'Competitor Matrix', icon: '📈', color: 'bg-indigo-100 text-indigo-800' },
  { id: 'run',               labelAr: 'تشغيل',         labelEn: 'Run',             icon: '🤖', color: 'bg-neutral-100 text-neutral-700' },
];

const SKILL_MAP: Record<string, SkillMeta> = Object.fromEntries(
  SKILLS.map((s) => [s.id, s]),
);

export function getSkill(id: string): SkillMeta {
  return SKILL_MAP[id] ?? SKILL_MAP['run']!;
}
