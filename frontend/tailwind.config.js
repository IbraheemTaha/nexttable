/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ['./templates/**/*.html'],
  theme: {
    extend: {
      colors: {
        // Ember: a warm terracotta accent standing in for the host stand /
        // service-industry domain, instead of the default blue/indigo.
        ember: {
          50: '#fdf4ed',
          100: '#fbe6d5',
          200: '#f5c9a6',
          300: '#eea56d',
          400: '#e57f3d',
          500: '#d9611f',
          600: '#bd4a16',
          700: '#963a15',
          800: '#7a3117',
          900: '#652a16',
        },
      },
      fontFamily: {
        // Fraunces for headings gives the app a hospitality/print-menu
        // character; Source Sans for UI body keeps dense tables legible.
        display: ['"Fraunces"', 'ui-serif', 'Georgia', 'serif'],
        sans: ['"Source Sans 3"', 'ui-sans-serif', 'system-ui', 'sans-serif'],
      },
    },
  },
  plugins: [],
};
