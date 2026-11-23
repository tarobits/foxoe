import { defineConfig } from 'vite';
import vue from '@vitejs/plugin-vue';
import { copyFileSync } from 'node:fs';

export default defineConfig({
  plugins: [vue(), { name: 'foxoe-license', closeBundle() { copyFileSync('LICENSE', 'dist/LICENSE'); } }],
  server: { proxy: {
    '/api': { target: 'http://127.0.0.1:8765', headers: { Origin: 'http://127.0.0.1:8765' }, changeOrigin: true },
    '/sdk.js': 'http://127.0.0.1:8765',
  } },
  build: { target: 'es2022' },
});
