// Maps action_type strings (from backend `describeAction`) to emoji icons.
const ACTION_ICONS: Record<string, string> = {
  navigate:         '🌐',
  click:            '👆',
  type:             '⌨️',
  scroll:           '📜',
  screenshot:       '📷',
  extract:          '📦',
  search:           '🔍',
  wait:             '⏳',
  submit:           '📤',
  fill:             '✏️',
  select:           '🔽',
  hover:            '🖱️',
  download:         '⬇️',
  upload:           '⬆️',
  close_tab:        '✕',
  open_tab:         '➕',
  switch_tab:       '↔️',
  research_round:   '🔎',
  synthesis:        '🧠',
  perception:       '👁️',
  decision:         '🤔',
  plan:             '📋',
  login:            '🔐',
  signup:           '📝',
  verify:           '✅',
  fallback:         '🤖',
};

interface ActionIconProps {
  actionType: string;
  className?: string;
}

export function ActionIcon({ actionType, className = '' }: ActionIconProps) {
  const icon = ACTION_ICONS[actionType] ?? ACTION_ICONS['fallback']!;
  return (
    <span className={`text-base leading-none ${className}`} role="img" aria-label={actionType}>
      {icon}
    </span>
  );
}
