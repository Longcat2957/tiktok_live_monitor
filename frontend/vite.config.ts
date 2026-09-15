import { sveltekit } from '@sveltejs/kit/vite';
import { defineConfig } from 'vitest/config';

const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';
export default defineConfig({
  plugins: [sveltekit()],
  server: { proxy: { '/ws': { target: backend, ws: true }, '/config': backend, '/health': backend } },
  test: { include: ['src/**/*.test.ts'], environment: 'node' }
});
