export interface SlashCommand {
  command: string;
  skill: string;
  labelAr: string;
}

export const SLASH_COMMANDS: SlashCommand[] = [
  { command: '/search',    skill: 'research',        labelAr: 'بحث'          },
  { command: '/explore',   skill: 'explore',          labelAr: 'استكشاف'      },
  { command: '/clone',     skill: 'clone',            labelAr: 'نسخ صفحة'    },
  { command: '/site',      skill: 'site_clone',       labelAr: 'نسخ موقع'    },
  { command: '/login',     skill: 'login',            labelAr: 'دخول'         },
  { command: '/signup',    skill: 'signup',           labelAr: 'اشتراك'       },
  { command: '/md',        skill: 'md_writer',        labelAr: 'تقرير MD'    },
  { command: '/html',      skill: 'html_artifact',    labelAr: 'صفحة HTML'   },
  { command: '/code',      skill: 'code_artifact',    labelAr: 'كود'          },
  { command: '/diagram',   skill: 'mermaid_diagram',  labelAr: 'مخطط'         },
  { command: '/summary',   skill: 'summarize',        labelAr: 'تلخيص'        },
  { command: '/translate', skill: 'translate',        labelAr: 'ترجمة'        },
];

export function parseSlashCommand(text: string): string | null {
  const lower = text.trim().toLowerCase();
  const match = SLASH_COMMANDS.find(
    (c) => lower === c.command || lower.startsWith(c.command + ' '),
  );
  return match?.skill ?? null;
}

export function getSuggestedCommands(text: string): SlashCommand[] {
  if (!text.startsWith('/')) return [];
  const lower = text.toLowerCase();
  return SLASH_COMMANDS.filter((c) => c.command.startsWith(lower));
}
