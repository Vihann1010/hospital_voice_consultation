#!/usr/bin/env node
/**
 * Runs AFTER `next build` (production only). Minification already happened via Next/SWC; this pass additionally
 * mangles identifiers, strings and control flow in our own chunks so a copied bundle is slow and unpleasant to
 * read, on top of what minification alone gives. It is NOT "unbreakable" — any obfuscator can be deobfuscated
 * given enough time — it raises the cost of casual copying, nothing more. Never run this on a dev build: it
 * breaks source maps and makes our own bug reports from staff useless to debug.
 *
 * Deliberately excluded:
 *   - node_modules chunks (vendor code; obfuscating React itself gains nothing and risks breakage)
 *   - anything already proven correct by the obfuscator's own "dead code injection" being OFF (keeps output
 *     size and cold-start time sane on the node PCs, which are weak)
 */
import { createHash } from "node:crypto";
import { readFileSync, writeFileSync, existsSync } from "node:fs";
import { glob } from "glob";
import JavaScriptObfuscator from "javascript-obfuscator";

const ROOT = ".next/static/chunks";
if (!existsSync(ROOT)) {
  console.error(`obfuscate-build: ${ROOT} not found — run "next build" first`);
  process.exit(1);
}

const OPTIONS = {
  compact: true,
  controlFlowFlattening: true,
  controlFlowFlatteningThreshold: 0.4, // a lighter touch: full flattening on everything noticeably slows page load on weak node PCs
  deadCodeInjection: false,
  identifierNamesGenerator: "mangled",
  renameGlobals: false, // would try to touch real globals the chunk relies on (self.webpackChunk_N_E etc.); see the IIFE wrap below instead
  rotateStringArray: true,
  selfDefending: true, // breaks if someone reformats/beautifies the file, without needing eval-based anti-debug traps
  stringArray: true,
  stringArrayEncoding: ["base64"],
  stringArrayThreshold: 0.75,
  transformObjectKeys: false, // Next's module registry depends on exact key names; this would break chunk loading
  disableConsoleOutput: true,
};

const files = await glob(`${ROOT}/**/*.js`, { ignore: [`${ROOT}/**/webpack-*.js`, `${ROOT}/**/framework-*.js`] });
if (files.length === 0) {
  console.error("obfuscate-build: no chunk files matched — check the glob/path if Next's output layout changed");
  process.exit(1);
}

let bytesIn = 0, bytesOut = 0;
for (const file of files) {
  const src = readFileSync(file, "utf8");
  bytesIn += src.length;
  // Next ships these chunks as classic (non-module) <script> tags, which all share ONE global top-level
  // scope in the browser. Obfuscating each file on its own can pick the same short name (e.g. `d`) for an
  // internal helper in two different chunks, and the second declaration then throws "already declared" —
  // this broke the whole app the first time, caught only by actually loading a page, not by the build
  // succeeding. A per-file prefix keeps every chunk's top-level names unique across the whole bundle.
  const prefix = "_e" + createHash("sha256").update(file).digest("hex").slice(0, 6) + "_";
  const obfuscated = JavaScriptObfuscator.obfuscate(src, { ...OPTIONS, identifiersPrefix: prefix }).getObfuscatedCode();
  // Next loads every chunk as a classic (non-module) <script>, and ALL of those share one top-level lexical
  // scope in the browser — that is true before our pass touches anything. Two files landing on the same
  // top-level `const`/`let` name (even something the minifier, not us, produced — e.g. a plain `d`) then
  // throws "Identifier already declared" and takes the whole app down. identifiersPrefix above only renames
  // the obfuscator's OWN generated names; this wrap is what actually makes it safe regardless: putting an
  // IIFE around the whole file turns its top level into a function scope, so nothing in it can collide with
  // another chunk's top level, no matter what either file names its variables.
  const out = `(function(){${obfuscated}})();`;
  bytesOut += out.length;
  writeFileSync(file, out, "utf8");
}
console.log(`obfuscate-build: ${files.length} chunk(s), ${(bytesIn / 1e6).toFixed(1)}MB -> ${(bytesOut / 1e6).toFixed(1)}MB`);
