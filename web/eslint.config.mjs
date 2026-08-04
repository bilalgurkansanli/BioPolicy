import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

const eslintConfig = defineConfig([
  ...nextVitals,
  ...nextTs,
  // Override default ignores of eslint-config-next.
  globalIgnores([
    // Default ignores of eslint-config-next:
    ".next/**",
    "out/**",
    "build/**",
    "next-env.d.ts",
    // Vendored: the pdf.js worker is copied in from node_modules by
    // `scripts/copy-pdf-worker.mjs`. Linting a minified third-party bundle
    // produces over a thousand findings about code nobody here will edit.
    "public/pdf.worker.min.mjs",
  ]),
]);

export default eslintConfig;
