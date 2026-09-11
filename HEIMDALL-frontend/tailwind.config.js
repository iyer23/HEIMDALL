/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        /* Light warm surfaces (token names kept for compatibility) */
        ink: {
          950: '#F8F9F6',
          900: '#FFFFFF',
          850: '#FFFFFF',
          800: '#EDEFE9',
          700: '#DDE2D6',
          600: '#C9D1C0',
        },
        mist: {
          DEFAULT: '#5A6153',
          dim: '#8A9080',
          bright: '#1F2420',
        },
        /* Primary accent: Dark Olive */
        vigil: {
          200: '#5C6B47',
          300: '#3F4A32',
          400: '#4A5639',
          500: '#3F4A32',
          600: '#333C28',
        },
        /* Semantic status colors */
        ok:   '#356859',
        warn: '#C47A2C',
        bad:  '#B54848',
      },
      fontFamily: {
        display: ['"Barlow Condensed"', 'Impact', 'sans-serif'],
        sans:    ['"IBM Plex Sans"', 'system-ui', 'sans-serif'],
        mono:    ['"IBM Plex Mono"', 'ui-monospace', 'monospace'],
      },
      boxShadow: {
        panel: '0 1px 2px rgba(31,36,32,0.05), 0 14px 36px -16px rgba(31,36,32,0.16)',
        glow:  '0 8px 28px -8px rgba(63,74,50,0.35)',
      },
    },
  },
  plugins: [],
}
