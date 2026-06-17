// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Bundles the three MV3 entry points to the flat names manifest.json references
// and copies the static assets into dist/. Run: `npm run build`. The unpacked
// extension to "Load unpacked" is the dist/ directory.

import { build } from "esbuild";
import { cp, mkdir } from "node:fs/promises";

const OUT = "dist";

await mkdir(OUT, { recursive: true });

await build({
  entryPoints: {
    background: "src/background.ts",
    content: "src/content/index.ts",
    offscreen: "src/offscreen.ts",
  },
  bundle: true,
  format: "esm",
  target: "chrome120",
  outdir: OUT,
  logLevel: "info",
});

for (const asset of ["manifest.json", "offscreen.html"]) {
  await cp(asset, `${OUT}/${asset}`);
}

console.log(`built -> ${OUT}/ (load this dir as the unpacked extension)`);
