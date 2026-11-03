// Bundles the extension into dist/ (load that folder in chrome://extensions).
import { build } from "esbuild";
import { cpSync, mkdirSync, rmSync } from "node:fs";

rmSync("dist", { recursive: true, force: true });
mkdirSync("dist");
await build({
  entryPoints: { background: "src/background.ts", content: "src/content.ts", popup: "src/popup.ts" },
  bundle: true,
  outdir: "dist",
  format: "iife",
  target: "chrome120",
  minify: true,
  legalComments: "none",
});
for (const f of ["manifest.json", "popup.html", "icons"]) cpSync(f, `dist/${f}`, { recursive: true });
console.log("Built extension into dist/");
