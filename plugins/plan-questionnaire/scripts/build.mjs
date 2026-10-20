import { build } from "esbuild";
import { mkdir, readFile, writeFile, copyFile } from "node:fs/promises";
await mkdir("dist", { recursive: true });
const client = await build({ entryPoints: ["src/widget.mjs"], bundle: true, write: false,
  format: "iife", platform: "browser", target: "es2022", minify: true });
const css = await readFile("src/widget.css", "utf8");
await writeFile("dist/widget.html", `<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>方案讨论问卷</title><style>${css}</style></head>
<body><main id="app" aria-live="polite"><p class="loading">正在连接问卷…</p></main>
<script>${client.outputFiles[0].text.replaceAll("</script", "<\\/script")}</script></body></html>`);
await build({ entryPoints: ["src/server.mjs"], outfile: "dist/server.mjs", bundle: true,
  platform: "node", format: "esm", target: "node22", minify: false,
  banner: { js: 'import { createRequire as __createRequire } from "node:module"; const require = __createRequire(import.meta.url);' } });
await copyFile("examples/current-question.json", "dist/example.json");
console.log("Built self-contained MCP server and questionnaire UI.");
