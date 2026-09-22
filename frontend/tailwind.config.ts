import type { Config } from 'tailwindcss'

/**
 * Clinical workstation palette: deep navy surfaces, teal for AI activity,
 * restrained accents for speaker roles and review states.
 */
export default {
  darkMode: 'class',
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        navy: {
          50: '#f2f6fa',
          100: '#e2eaf3',
          200: '#c3d3e5',
          300: '#94b1cf',
          400: '#5d86b1',
          500: '#3c6795',
          600: '#2c507a',
          700: '#254163',
          800: '#1c3350',
          900: '#132339',
          950: '#0b1726',
        },
        teal: {
          50: '#effcf9',
          100: '#c7f5ec',
          200: '#94e9dc',
          300: '#5bd6c7',
          400: '#2fbcae',
          500: '#159f94',
          600: '#0d8078',
          700: '#0f6660',
          800: '#10514e',
          900: '#114341',
        },
        pastel: {
          mint: '#D8ECE5',
          mintText: '#134E4A',
          mintBorder: '#BCE1D6',
          rose: '#FCE1E8',
          roseText: '#831843',
          roseBorder: '#F9C8D4',
          butter: '#FEF0C3',
          butterText: '#78350F',
          butterBorder: '#FDE68A',
          lavender: '#E5DEFA',
          lavenderText: '#4C1D95',
          lavenderBorder: '#DDD6FE',
          sky: '#D9EDF8',
          skyText: '#0369A1',
          skyBorder: '#BAE6FD',
          canvas: '#EDF2F6',
          dark: '#18181B',
        },
        role: {
          doctor: '#0f766e',
          patient: '#0284c7',
          nurse: '#7c3aed',
          staff: '#b45309',
          background: '#64748b',
          unknown: '#94a3b8',
        },
        state: {
          live: '#e11d48',
          processing: '#d97706',
          ai: '#0d9488',
          review: '#b45309',
          approved: '#15803d',
          error: '#dc2626',
        },
      },
      fontFamily: {
        sans: ['"Plus Jakarta Sans"', 'Inter', 'Segoe UI', 'system-ui', 'sans-serif'],
        mono: ['"JetBrains Mono"', 'Consolas', 'ui-monospace', 'monospace'],
      },
      fontSize: {
        '2xs': ['0.6875rem', { lineHeight: '1rem' }],
      },
      boxShadow: {
        panel: '0 1px 2px rgba(15, 35, 57, 0.06), 0 1px 3px rgba(15, 35, 57, 0.04)',
        raised: '0 4px 16px rgba(15, 35, 57, 0.10)',
      },
      keyframes: {
        'pulse-dot': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.25' },
        },
        'slide-in': {
          from: { opacity: '0', transform: 'translateY(6px)' },
          to: { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'fade-in-down': {
          '0%': { opacity: '0', transform: 'translateY(-8px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'tab-slide': {
          '0%': { opacity: '0', transform: 'translateX(8px)' },
          '100%': { opacity: '1', transform: 'translateX(0)' },
        },
        'scale-spring': {
          '0%': { opacity: '0', transform: 'scale(0.97)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
        'glow-pulse': {
          '0%, 100%': {
            boxShadow: '0 0 15px -3px rgba(20, 184, 166, 0.4), 0 0 6px -2px rgba(20, 184, 166, 0.2)',
          },
          '50%': {
            boxShadow: '0 0 25px 2px rgba(20, 184, 166, 0.6), 0 0 12px 0px rgba(20, 184, 166, 0.3)',
          },
        },
        'ecg-draw': {
          '0%': { strokeDashoffset: '200' },
          '100%': { strokeDashoffset: '0' },
        },
        'shimmer': {
          '0%': { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
        'equalizer': {
          '0%, 100%': { height: '4px' },
          '50%': { height: '18px' },
        },
      },
      animation: {
        'pulse-dot': 'pulse-dot 1.4s ease-in-out infinite',
        'slide-in': 'slide-in 180ms ease-out',
        'fade-in-up': 'fade-in-up 240ms cubic-bezier(0.16, 1, 0.3, 1)',
        'fade-in-down': 'fade-in-down 240ms cubic-bezier(0.16, 1, 0.3, 1)',
        'tab-slide': 'tab-slide 220ms cubic-bezier(0.16, 1, 0.3, 1)',
        'scale-spring': 'scale-spring 200ms cubic-bezier(0.16, 1, 0.3, 1)',
        'glow-pulse': 'glow-pulse 2.5s ease-in-out infinite',
        'ecg-draw': 'ecg-draw 1.8s linear infinite',
        'shimmer': 'shimmer 2s linear infinite',
        'equalizer-1': 'equalizer 0.8s ease-in-out infinite 0.1s',
        'equalizer-2': 'equalizer 0.8s ease-in-out infinite 0.3s',
        'equalizer-3': 'equalizer 0.8s ease-in-out infinite 0.15s',
        'equalizer-4': 'equalizer 0.8s ease-in-out infinite 0.4s',
      },
    },
  },
  plugins: [],
} satisfies Config
