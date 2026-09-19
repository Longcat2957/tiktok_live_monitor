import adapter from '@sveltejs/adapter-static';
import { vitePreprocess } from '@sveltejs/vite-plugin-svelte';

/** @type {import('@sveltejs/kit').Config} */
const config = {
    preprocess: vitePreprocess(),
    kit: {
        adapter: adapter(),
        version: { pollInterval: 30_000 },
        typescript: {
            config(config) {
                config.include.push(
                    '../e2e/**/*.ts',
                    '../scripts/**/*.mjs',
                    '../*.config.js',
                    '../*.config.ts',
                );
            },
        },
    },
};

export default config;
