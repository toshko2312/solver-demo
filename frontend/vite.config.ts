import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// The solver runs as a separate service. In dev we proxy /api to it so the
// browser never has to care about a second origin; VITE_API_URL overrides the
// base if you want to point at a solver somewhere else.
const SOLVER_URL = process.env.SOLVER_URL ?? 'http://localhost:8000';

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // The seed dataset lives in ../shared so the solver's tests and the UI use
    // exactly the same numbers.
    fs: { allow: ['..'] },
    proxy: {
      '/api': {
        target: SOLVER_URL,
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
});
