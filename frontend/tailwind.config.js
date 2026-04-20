/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        fantasy: {
          dark: '#0f172a',
          panel: '#1e293b',
          accent: '#b45309',
          text: '#e2e8f0',
          dim: '#94a3b8'
        }
      }
    },
  },
  plugins: [],
}
