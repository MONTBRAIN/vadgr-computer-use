// Copyright 2026 Victor Santiago Montaño Diaz
// Licensed under the Apache License, Version 2.0.
//
// Bundles the MV3 entry points to the flat names manifest.json references and
// copies the static assets into dist/. Run: `npm run build`. The unpacked
// extension to "Load unpacked" is the dist/ directory.
//
// Format matters per surface:
//   - background (service worker) is an ES module (manifest `type: "module"`).
//   - offscreen.js is loaded by offscreen.html via `<script type="module">`.
//   - the CONTENT SCRIPT is a *classic* script — MV3 content_scripts cannot be
//     modules, so a top-level `export`/`import` throws on load and the script's
//     onMessage listener never registers ("Receiving end does not exist"). It
//     must be built as IIFE.

import { build } from "esbuild";
import { cp, mkdir, readFile } from "node:fs/promises";

const OUT = "dist";
const common = { bundle: true, target: "chrome120", outdir: OUT, logLevel: "info" };

await mkdir(OUT, { recursive: true });

// ES modules: service worker + offscreen.
await build({
  ...common,
  entryPoints: { background: "src/background.ts", offscreen: "src/offscreen.ts" },
  format: "esm",
});

// Classic script: the content script (no top-level export/import allowed).
await build({
  ...common,
  entryPoints: { content: "src/content/index.ts" },
  format: "iife",
});

for (const asset of ["manifest.json", "offscreen.html"]) {
  await cp(asset, `${OUT}/${asset}`);
}

// Guard: the content script must not ship top-level ESM syntax, or it fails to
// load in the page and DOM ops break at runtime (unit tests can't catch this).
const contentJs = await readFile(`${OUT}/content.js`, "utf8");
if (/^\s*export[\s{]/m.test(contentJs) || /^\s*import[\s{*]/m.test(contentJs)) {
  throw new Error(
    "content.js contains top-level ESM syntax — content scripts must be IIFE",
  );
}

console.log(`built -> ${OUT}/ (load this dir as the unpacked extension)`);
