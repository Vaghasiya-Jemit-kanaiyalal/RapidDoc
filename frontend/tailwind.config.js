/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#EEF4FF',   // Light blue (badge bg)
          100: '#e1ebff',
          200: '#c7daff',
          300: '#a3beff',
          400: '#7a9bff',
          500: '#4F6BFF',  // Gradient start
          600: '#365CFF',  // Primary brand color
          700: '#2E4CFF',  // Gradient end
          800: '#263299',
          900: '#232d7a',
        },
        ink: '#0F172A',
        secondary: '#64748B',
        borderline: '#E5E7EB',
        accentPurple: '#8B5CF6',
        accentGreen: '#22C55E',
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', '-apple-system', 'sans-serif'],
        script: ['Caveat', 'cursive'],
      },
      boxShadow: {
        'soft-blue': '0 20px 60px rgba(72, 110, 255, 0.12)',
        'floating': '0 15px 40px rgba(0, 0, 0, 0.08)',
        'card': '0 4px 24px rgba(15, 23, 42, 0.06)',
      },
      keyframes: {
        float: {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-10px)' },
        },
        'float-slow': {
          '0%, 100%': { transform: 'translateY(0px) rotate(0deg)' },
          '50%': { transform: 'translateY(-14px) rotate(1.5deg)' },
        },
        'float-spin': {
          '0%, 100%': { transform: 'translateY(0px) rotate(-3deg)' },
          '50%': { transform: 'translateY(-8px) rotate(-2deg)' },
        },
      },
      animation: {
        float: 'float 4s ease-in-out infinite',
        'float-slow': 'float-slow 5s ease-in-out infinite',
        'float-spin': 'float-spin 5s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
