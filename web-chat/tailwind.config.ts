import type { Config } from 'tailwindcss'
import typography from '@tailwindcss/typography'

const config: Config = {
  darkMode: 'class',
  content: [
    './index.html',
    './src/**/*.{ts,tsx}',
  ],
  theme: {
    extend: {
      fontFamily: {
        arabic: ['Tajawal', 'sans-serif'],
        sans: ['Inter', 'sans-serif'],
        mono: ['JetBrains Mono', 'monospace'],
      },
      maxWidth: {
        chat: '820px',
      },
      colors: {
        accent: {
          DEFAULT: '#4f46e5', // indigo-600
          hover: '#4338ca',
        },
      },
    },
  },
  plugins: [typography],
}

export default config
