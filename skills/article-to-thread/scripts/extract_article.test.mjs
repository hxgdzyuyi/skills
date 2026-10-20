import assert from 'node:assert/strict';
import { execFile } from 'node:child_process';
import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import http from 'node:http';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { promisify } from 'node:util';
import test from 'node:test';
import { extractHtml, ExtractionError } from './extract_article.mjs';

const run = promisify(execFile);
const cli = fileURLToPath(new URL('./extract_article.mjs', import.meta.url));
const sourceUrl = 'https://example.com/articles/source';
const body = 'The research compares two architecture choices and explains the measured performance. Each design uses a different strategy for memory management, deployment, and failure recovery. The authors report that a smaller number of components makes their system easier to operate.';

test('WeChat uses the article container, resolves lazy images, and preserves structure', () => {
  const article = extractHtml(`<!doctype html><html lang="zh-CN"><head><title>页面标题</title></head><body>
  <h1 id="activity-name">测试文章</h1><span id="js_name">测试作者</span><nav>不要收录导航</nav>
  <div id="js_content"><h2>架构选择</h2><p>${body}</p>
  <figure><img data-src="/media/architecture.png" src="data:image/gif;base64,AA" alt="系统架构图" width="48" height="48"><figcaption>原文的架构示意</figcaption></figure>
  <p><img data-original="/media/architecture.png" alt="重复图"></p>
  <img src="/tracking-pixel.gif" width="1" height="1"><img src="/assets/avatar.png">
  <table><thead><tr><th>方案</th><th>成本</th></tr></thead><tbody><tr><td>A</td><td>10</td></tr></tbody></table>
  <ol><li>检查原文</li><li>比较数据</li></ol><pre><code>console.log('example');</code></pre>
  <script>document.querySelector('h2').textContent='EXECUTED SECRET';</script></div><footer>不要收录页脚</footer>
  </body></html>`, { sourceUrl });
  assert.equal(article.kind, 'article');
  assert.equal(article.extraction.method, 'wechat');
  assert.equal(article.title, '测试文章');
  assert.equal(article.author, '测试作者');
  assert.equal(article.language, 'zh-CN');
  assert.equal(article.images.length, 1);
  assert.equal(article.images[0].url, 'https://example.com/media/architecture.png');
  assert.match(article.images[0].id, /^img-[a-f0-9]{16}$/);
  assert.equal(article.images[0].caption, '原文的架构示意');
  assert.match(article.images[0].context, /架构示意/);
  assert.match(article.content_markdown, /## 架构选择/);
  assert.match(article.content_markdown, /\| 方案 \| 成本 \|/);
  assert.match(article.content_markdown, /1\.\s+检查原文/);
  assert.match(article.content_markdown, /```/);
  assert.doesNotMatch(article.content_markdown, /EXECUTED SECRET|不要收录|tracking-pixel|avatar\.png/);
});

test('generic article selects Readability and the highest-resolution srcset', () => {
  const article = extractHtml(`<html lang="en"><head><title>Architecture benchmark</title><meta name="author" content="Ada"></head><body>
  <nav>Home Projects Contact</nav><article><h1>Architecture benchmark</h1><h2>Measurement</h2>
  <p>${body}</p><p>${body}</p><figure><img src="/small.png" srcset="/small.png 320w, /large.png 1280w" alt="Measurement chart"><figcaption>Measurements in milliseconds</figcaption></figure>
  <p><a href="../details">Details</a></p></article><footer>Unrelated legal text</footer></body></html>`, { sourceUrl });
  assert.equal(article.extraction.method, 'readability');
  assert.equal(article.kind, 'article');
  assert.equal(article.images[0].url, 'https://example.com/large.png');
  assert.match(article.content_markdown, /https:\/\/example\.com\/details/);
  assert.doesNotMatch(article.content_markdown, /Unrelated legal text/);
});

test('image IDs stay stable across invocations and fragments are canonicalized', () => {
  const html = `<h1>图片文章</h1><div id="js_content"><p>${body}</p><img src="/diagram.png#first"><img src="/diagram.png#second"></div>`;
  const first = extractHtml(html, { sourceUrl });
  const second = extractHtml(html, { sourceUrl });
  assert.equal(first.images.length, 1);
  assert.equal(first.images[0].id, second.images[0].id);
  assert.equal(first.images[0].url, 'https://example.com/diagram.png');
});

test('metadata-only page is a link card with empty body fields', () => {
  const article = extractHtml(`<html><head><meta property="og:title" content="Card title"><meta name="description" content="A brief publisher description, not the original article."><meta property="og:image" content="/preview.jpg"></head><body><div id="app"></div></body></html>`, { sourceUrl });
  assert.equal(article.kind, 'link_card');
  assert.equal(article.extraction.method, 'metadata_only');
  assert.equal(article.extraction.body_available, false);
  assert.equal(article.content_text, '');
  assert.equal(article.content_markdown, '');
  assert.match(article.description, /not the original article/);
  assert.equal(article.images[0].url, 'https://example.com/preview.jpg');
  assert.match(article.extraction.warnings[0], /not the full article/);
});

test('text-only CLI omits all image output while retaining author, prose, tables, and captions', async t => {
  const folder = await mkdtemp(path.join(os.tmpdir(), 'article-to-thread-text-only-'));
  t.after(() => rm(folder, { recursive: true, force: true }));
  const input = path.join(folder, 'input.html');
  const output = path.join(folder, 'result');
  await writeFile(input, `<html><head><title>纯文本文章</title><meta name="author" content="原文作者"><meta property="og:image" content="/card-preview.jpg"></head><body>
  <div id="js_content"><h2>正文要点</h2><p>${body}</p>
  <figure><picture><source srcset="/diagram-large.png 1280w"><img src="/diagram-small.png" data-src="/original-diagram.png" alt="IMAGE ALT MUST NOT BE COLLECTED"></picture><figcaption>图注文本仍然保留：方案 A 与方案 B 的对比。</figcaption></figure>
  <table><thead><tr><th>方案</th><th>成本</th></tr></thead><tbody><tr><td>A</td><td>10</td></tr></tbody></table>
  <p>图片之后的正文也应保留。</p></div></body></html>`);
  await run(process.execPath, [cli, '--url', sourceUrl, '--html-file', input, '--out', output, '--text-only']);
  const article = JSON.parse(await readFile(path.join(output, 'article.json'), 'utf8'));
  const source = await readFile(path.join(output, 'source.md'), 'utf8');
  assert.equal(article.kind, 'article');
  assert.equal(article.author, '原文作者');
  assert.equal(article.extraction.text_only, true);
  assert.deepEqual(article.images, []);
  assert.match(article.content_markdown, /## 正文要点/);
  assert.match(article.content_markdown, /图注文本仍然保留/);
  assert.match(article.content_markdown, /\| 方案 \| 成本 \|/);
  assert.match(article.content_text, /图片之后的正文也应保留/);
  assert.match(source, /图注文本仍然保留/);
  assert.doesNotMatch(source + JSON.stringify(article), /!\[[^\]]*\]\(|<(?:img|picture|source)\b|diagram-(?:small|large)\.png|original-diagram\.png|IMAGE ALT MUST NOT BE COLLECTED|card-preview\.jpg/);
  const card = extractHtml('<meta name="description" content="A publisher excerpt"><meta property="og:image" content="/preview.jpg">', { sourceUrl, textOnly: true });
  assert.equal(card.kind, 'link_card');
  assert.deepEqual(card.images, []);
});

test('unsupported pages fail with actionable errors and no fabricated body', () => {
  assert.throws(() => extractHtml('<title>Interactive app</title><div id="app"></div>', { sourceUrl }), error => error instanceof ExtractionError && error.code === 'BODY_UNAVAILABLE' && error.suggestion.includes('--html-file'));
  assert.throws(() => extractHtml('<title>Just a moment...</title><p>Enable JavaScript and cookies</p>', { sourceUrl }), error => error.code === 'ACCESS_BLOCKED');
  assert.throws(() => extractHtml('<p>Invalid URL</p>', { sourceUrl: 'file:///private/article.html' }), error => error.code === 'INVALID_URL');
});

test('local CLI writes artifacts and keeps source content out of stdout', async t => {
  const folder = await mkdtemp(path.join(os.tmpdir(), 'article-to-thread-test-'));
  t.after(() => rm(folder, { recursive: true, force: true }));
  const input = path.join(folder, 'input.html');
  const output = path.join(folder, 'result');
  await writeFile(input, `<title>Private source fixture</title><div id="js_content"><p>${body} DO NOT LOG SOURCE TEXT</p></div>`);
  const result = await run(process.execPath, [cli, '--url', sourceUrl, '--html-file', input, '--out', output]);
  const article = JSON.parse(await readFile(path.join(output, 'article.json'), 'utf8'));
  assert.equal(article.extraction.input, 'html_file');
  assert.equal(article.source_url, sourceUrl);
  assert.match(await readFile(path.join(output, 'source.md'), 'utf8'), /DO NOT LOG SOURCE TEXT/);
  assert.doesNotMatch(result.stdout + result.stderr, /DO NOT LOG SOURCE TEXT|Private source fixture/);
  assert.match(result.stdout, /kind=article/);
});

test('CLI records extraction failure in its output folder', async t => {
  const folder = await mkdtemp(path.join(os.tmpdir(), 'article-to-thread-error-'));
  t.after(() => rm(folder, { recursive: true, force: true }));
  const input = path.join(folder, 'empty.html');
  const output = path.join(folder, 'result');
  await writeFile(input, '<title>JavaScript app</title><div id="app"></div>');
  await assert.rejects(run(process.execPath, [cli, '--url', sourceUrl, '--html-file', input, '--out', output]), error => error.code === 1 && error.stderr.includes('BODY_UNAVAILABLE'));
  const failure = JSON.parse(await readFile(path.join(output, 'extraction-error.json'), 'utf8'));
  assert.equal(failure.error, 'BODY_UNAVAILABLE');
  assert.match(failure.suggestion, /--html-file/);
  await assert.rejects(readFile(path.join(output, 'article.json')), { code: 'ENOENT' });
});

test('HTTP CLI follows a redirect and never fetches images or page scripts', async t => {
  const requests = [];
  const server = http.createServer((request, response) => {
    requests.push(request.url);
    if (request.url === '/redirect') { response.writeHead(302, { location: '/article' }); response.end(); return; }
    if (request.url === '/article') {
      response.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
      response.end(`<title>Local HTTP fixture</title><article><p>${body}</p><p>${body}</p><img src="/illustration.jpg" alt="Architecture diagram"><script src="/external.js"></script></article>`);
      return;
    }
    response.writeHead(404); response.end();
  });
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  t.after(() => new Promise(resolve => server.close(resolve)));
  const folder = await mkdtemp(path.join(os.tmpdir(), 'article-to-thread-http-'));
  t.after(() => rm(folder, { recursive: true, force: true }));
  const url = `http://127.0.0.1:${server.address().port}/redirect`;
  await run(process.execPath, [cli, '--url', url, '--out', folder]);
  const article = JSON.parse(await readFile(path.join(folder, 'article.json'), 'utf8'));
  assert.equal(article.source_url, url);
  assert.equal(article.resolved_url, url.replace('/redirect', '/article'));
  assert.equal(article.images.length, 1);
  assert.deepEqual(requests, ['/redirect', '/article']);
});
