/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  darkMode: 'class',
  theme: {
    extend: {
      colors: {
        at: {
          ink: '#181d26',
          body: '#333840',
          muted: '#41454d',
          hairline: '#dddddd',
          canvas: '#ffffff',
          'surface-soft': '#f8fafc',
          'surface-strong': '#e0e2e6',
          'surface-dark': '#181d26',
          coral: '#aa2d00',
          forest: '#0a2e0e',
          cream: '#f5e9d4',
          peach: '#fcab79',
          mint: '#a8d8c4',
          yellow: '#f4d35e',
          mustard: '#d9a441',
          link: '#1b61c9',
          success: '#006400',
        }
      },
      animation: {
        'pulse-slow': 'pulse 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'slide-in': 'slideIn 0.3s cubic-bezier(0.32,0.72,0,1)',
        'fade-in': 'fadeIn 0.2s ease-out',
      },
      keyframes: {
        slideIn: { '0%': { transform: 'translateX(100%)', opacity: '0' }, '100%': { transform: 'translateX(0)', opacity: '1' } },
        fadeIn: { '0%': { opacity: '0', transform: 'translateY(-4px)' }, '100%': { opacity: '1', transform: 'translateY(0)' } },
      },
    },
  },
  plugins: [],
}
