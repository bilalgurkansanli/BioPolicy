/**
 * Copy the pdf.js worker into `public/`.
 *
 * The worker has to be served as a separate file at a stable URL, and its
 * version must match the `pdfjs-dist` the app imports — a mismatch fails at
 * runtime with an error that does not mention versions. Copying it from
 * `node_modules` on every install and build means the two cannot drift, and it
 * avoids relying on bundler-specific handling of `new URL(..., import.meta.url)`.
 */

import { copyFile, mkdir } from "node:fs/promises";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const require = createRequire(import.meta.url);
const packageJson = require.resolve("pdfjs-dist/package.json");
const source = join(dirname(packageJson), "build", "pdf.worker.min.mjs");

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const destination = join(root, "public", "pdf.worker.min.mjs");

await mkdir(dirname(destination), { recursive: true });
await copyFile(source, destination);
console.log(`copied pdf.js worker -> ${destination}`);
