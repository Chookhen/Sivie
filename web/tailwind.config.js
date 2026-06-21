/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        // Layered dark-navy theme: a darker canvas with progressively
        // lighter elevated surfaces (so it reads as "dark, but not all dark").
        canvas: '#0e1626',
        panel: '#162034',
        'panel-2': '#1e2a44',
        'panel-3': '#243150',
        line: '#2b3a57',
        'line-soft': '#212d45',
        ink: '#e8edf6',
        muted: '#9aa8c2',
        faint: '#62718e',
        // Single professional accent used consistently for interactive UI.
        primary: '#3b82f6',
        'primary-strong': '#2563eb',
        'primary-soft': '#16233f',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      borderRadius: { card: '10px' },
      boxShadow: {
        card: '0 1px 2px rgba(0,0,0,0.3)',
        pop: '0 10px 30px rgba(2,6,23,0.55)',
      },
    },
  },
  plugins: [],
}
