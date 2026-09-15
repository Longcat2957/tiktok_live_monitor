import { sveltekit } from '@sveltejs/kit/vite';
import { functionsMixins } from 'vite-plugin-functions-mixins';
import { defineConfig } from 'vitest/config';

const backend = process.env.BACKEND_URL ?? 'http://127.0.0.1:8000';
export default defineConfig({
  // Restart Vite after changing CSS @function definitions; M3 components cache compiled styles.
  plugins: [sveltekit(), functionsMixins({ deps: ['m3-svelte'] })],
  server: { proxy: { '/ws': { target: backend, ws: true }, '/account': { target: backend, changeOrigin: false }, '/refresh': { target: backend, changeOrigin: false }, '/config': { target: backend, changeOrigin: false }, '/health': backend } },
  test: { include: ['src/**/*.test.ts'], environment: 'node' }
});
