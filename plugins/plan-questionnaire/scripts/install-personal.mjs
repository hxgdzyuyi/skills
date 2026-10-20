import { homedir } from "node:os";
import { join, relative, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { readFile, writeFile, mkdir, rename, copyFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";

const pluginRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const userRoot = homedir();
const sourcePath = "./" + relative(userRoot, pluginRoot);
if (sourcePath.startsWith("./..")) throw new Error("个人插件源必须位于用户目录内");
const cataloguePath = join(userRoot, ".agents/plugins/marketplace.json");
await mkdir(dirname(cataloguePath), { recursive: true });
let catalogue;
try { catalogue = JSON.parse(await readFile(cataloguePath, "utf8")); }
catch (e) {
  if (e.code !== "ENOENT") throw e;
  catalogue = { name: "personal", interface: { displayName: "Personal" }, plugins: [] };
}
const existing = catalogue.plugins.find(p => p.name === "plan-questionnaire");
if (existing && existing.source?.path !== sourcePath) throw new Error("已有同名插件指向其他位置，请先核对");
if (!existing) {
  const backupDirectory = join(userRoot, ".codex/backups/plan-questionnaire");
  await mkdir(backupDirectory, { recursive: true });
  try { await copyFile(cataloguePath, join(backupDirectory, `marketplace-${Date.now()}.json`)); }
  catch (e) { if (e.code !== "ENOENT") throw e; }
  catalogue.plugins.push({
    name: "plan-questionnaire", source: { source: "local", path: sourcePath },
    policy: { installation: "AVAILABLE", authentication: "ON_INSTALL" }, category: "Productivity",
  });
  const temporary = `${cataloguePath}.${process.pid}.tmp`;
  await writeFile(temporary, JSON.stringify(catalogue, null, 2) + "\n");
  await rename(temporary, cataloguePath);
}
const output = execFileSync("codex", ["plugin", "add", `plan-questionnaire@${catalogue.name}`, "--json"], { encoding: "utf8" });
console.log(output);
