import { build } from 'esbuild';
import { copyFile, mkdir } from 'node:fs/promises';
await mkdir('../app/static/assets', { recursive: true });
await build({ entryPoints: ['src/app.js'], bundle: true, minify: true,
  format: 'esm', target: ['es2022'], outfile: '../app/static/assets/app.js' });
await copyFile('index.html', '../app/static/index.html');
