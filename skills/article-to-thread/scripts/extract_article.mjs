#!/usr/bin/env node
/** Source extraction only. This program never runs page scripts or calls a model. */
import { createHash } from 'node:crypto';
import { mkdir, readFile, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';
import { Readability } from '@mozilla/readability';
import { JSDOM } from 'jsdom';
import TurndownService from 'turndown';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { gfm } = require('turndown-plugin-gfm');
const MAX_BYTES = 10 * 1024 * 1024;
const TIMEOUT_MS = 30_000;
const cleanText = value => (value ?? '').replace(/\s+/g, ' ').trim();

export class ExtractionError extends Error {
  constructor(code, message, suggestion) {
    super(message);
    this.name = 'ExtractionError';
    this.code = code;
    this.suggestion = suggestion;
  }
}

function httpUrl(value, base) {
  if (!value || /^(?:data|blob|javascript):/i.test(value.trim())) return null;
  try {
    const url = new URL(value.trim(), base);
    if (!['http:', 'https:'].includes(url.protocol)) return null;
    url.hash = '';
    return url.href;
  } catch { return null; }
}

function requireUrl(value) {
  const result = httpUrl(value);
  if (!result) throw new ExtractionError('INVALID_URL', 'A complete http(s) URL is required.', 'Provide --url https://example.com/article.');
  return result;
}

function meta(document, ...names) {
  for (const name of names) {
    for (const node of document.querySelectorAll('meta[name], meta[property]')) {
      if ([node.getAttribute('name'), node.getAttribute('property')].some(key => key?.toLowerCase() === name.toLowerCase())) {
        const value = cleanText(node.getAttribute('content'));
        if (value) return value;
      }
    }
  }
  return '';
}

function textOf(document, selector) {
  return cleanText(document.querySelector(selector)?.textContent);
}

function srcsetUrl(value, base) {
  if (!value) return null;
  const candidates = value.split(/\s*,\s*/).map(part => {
    const match = part.trim().match(/^(\S+)(?:\s+([\d.]+)(?:w|x))?$/);
    return match ? { url: httpUrl(match[1], base), size: Number(match[2] || 1) } : null;
  }).filter(item => item?.url);
  candidates.sort((a, b) => b.size - a.size);
  return candidates[0]?.url ?? null;
}

function imageUrl(node, base) {
  for (const attribute of ['data-src', 'data-original', 'data-lazy-src', 'data-actualsrc', 'data-echo', 'data-hi-res-src', 'lazy-src', 'data-url']) {
    const url = httpUrl(node.getAttribute(attribute), base);
    if (url) return url;
  }
  for (const attribute of ['data-srcset', 'srcset']) {
    const url = srcsetUrl(node.getAttribute(attribute), base);
    if (url) return url;
  }
  const picture = node.closest('picture');
  if (picture) {
    for (const source of picture.querySelectorAll('source')) {
      const url = srcsetUrl(source.getAttribute('data-srcset') || source.getAttribute('srcset'), base);
      if (url) return url;
    }
  }
  return httpUrl(node.getAttribute('src'), base);
}

function dimension(node, name) {
  const direct = node.getAttribute(name);
  if (direct && /^\d+(?:\.\d+)?(?:px)?$/.test(direct.trim())) return Number.parseFloat(direct);
  const match = node.getAttribute('style')?.match(new RegExp(`(?:^|;)\\s*${name}\\s*:\\s*([\\d.]+)px`, 'i'));
  return match ? Number(match[1]) : null;
}

function nearbyContext(node) {
  const figure = node.closest('figure');
  if (figure) return cleanText(figure.textContent).slice(0, 500);
  const parts = [];
  let container = node;
  for (let i = 0; i < 4 && container.parentElement; i++) {
    const parentText = cleanText(container.parentElement.textContent);
    if (parentText.length > 500) break;
    container = container.parentElement;
    if (parentText.length >= 20) { parts.push(parentText); break; }
  }
  const before = cleanText(container.previousElementSibling?.textContent);
  const after = cleanText(container.nextElementSibling?.textContent);
  return [...new Set([before.slice(-180), ...parts, after.slice(0, 180)].filter(Boolean))].join(' ').slice(0, 500);
}

function collectImages(root, base) {
  const images = [];
  const byUrl = new Map();
  for (const node of root.querySelectorAll('img')) {
    const url = imageUrl(node, base);
    const alt = cleanText(node.getAttribute('alt'));
    const caption = cleanText(node.closest('figure')?.querySelector('figcaption')?.textContent || node.getAttribute('title'));
    const width = dimension(node, 'width');
    const height = dimension(node, 'height');
    const importantDiagram = /diagram|chart|plot|figure|architecture|图表|架构|流程|示意/i.test(`${alt} ${caption}`);
    const tiny = (width !== null && width <= 2) || (height !== null && height <= 2)
      || (!importantDiagram && width !== null && height !== null && width <= 64 && height <= 64);
    const obviousIcon = !importantDiagram && url && /(?:^|[/_.-])(?:favicon|avatar|spacer|tracking[_-]?pixel|sprite|icon)(?:[/_.-]|\?|$)|\.ico(?:\?|$)/i.test(new URL(url).pathname);
    if (!url || tiny || obviousIcon) { node.remove(); continue; }
    const context = nearbyContext(node);
    const existing = byUrl.get(url);
    if (existing) {
      if (!existing.alt && alt) existing.alt = alt;
      if (!existing.caption && caption) existing.caption = caption;
      if (context.length > existing.context.length) existing.context = context;
    } else {
      const item = { id: `img-${createHash('sha256').update(url).digest('hex').slice(0, 16)}`, url, alt, caption, context, width, height };
      images.push(item);
      byUrl.set(url, item);
    }
    node.setAttribute('src', url);
    node.removeAttribute('srcset');
    node.setAttribute('alt', alt || caption || '原文配图');
  }
  return images;
}

function cleanArticle(root, base) {
  for (const node of root.querySelectorAll('script,style,noscript,iframe,object,embed,form,button,nav,footer,[aria-hidden="true"]')) node.remove();
  for (const link of root.querySelectorAll('a[href]')) {
    const original = link.getAttribute('href').trim();
    if (original.startsWith('#') || original.startsWith('mailto:')) continue;
    const url = httpUrl(original, base);
    if (url) link.setAttribute('href', url);
    else link.removeAttribute('href');
  }
  return root;
}

function toMarkdown(root) {
  const converter = new TurndownService({ headingStyle: 'atx', bulletListMarker: '-', codeBlockStyle: 'fenced', emDelimiter: '*' });
  converter.use(gfm);
  converter.remove(['script', 'style', 'noscript', 'iframe', 'object', 'embed']);
  converter.addRule('figureCaption', { filter: 'figcaption', replacement: content => content ? `\n\n*${content.trim()}*\n\n` : '' });
  return converter.turndown(root.innerHTML).replace(/\n{3,}/g, '\n\n').trim();
}

function wordCount(text) {
  return (text.match(/[\p{Script=Han}]/gu) ?? []).length + (text.replace(/[\p{Script=Han}]/gu, ' ').match(/[\p{L}\p{N}]+/gu) ?? []).length;
}

/** Extract an HTML string without executing any page code or loading subresources. */
export function extractHtml(html, { sourceUrl, resolvedUrl = sourceUrl, input = 'html_file', retrievedAt = new Date().toISOString(), textOnly = false } = {}) {
  sourceUrl = requireUrl(sourceUrl);
  resolvedUrl = requireUrl(resolvedUrl);
  const dom = new JSDOM(html, { url: resolvedUrl, contentType: 'text/html' });
  const document = dom.window.document;
  try {
    // Remove image nodes before Readability sees them; retain figure captions and surrounding text.
    if (textOnly) for (const node of document.querySelectorAll('img, picture source')) node.remove();
    let title = textOf(document, '#activity-name') || meta(document, 'og:title', 'twitter:title') || textOf(document, 'h1') || cleanText(document.title) || null;
    let author = meta(document, 'author', 'article:author', 'byl', 'byline') || textOf(document, '#js_name, .rich_media_meta_nickname') || null;
    let site = meta(document, 'og:site_name', 'application-name') || new URL(resolvedUrl).hostname;
    let language = cleanText(document.documentElement.getAttribute('lang')) || meta(document, 'content-language') || null;
    const description = meta(document, 'description', 'og:description', 'twitter:description') || null;
    const warnings = [];
    const bodyForCheck = document.body?.cloneNode(true);
    for (const node of bodyForCheck?.querySelectorAll('script,style,noscript') || []) node.remove();
    const bodyText = cleanText(bodyForCheck?.textContent);
    const blocker = /^(?:just a moment|access denied|attention required|安全验证|人机验证|访问受限)(?:[.!…\s]*(?:\|\s*Cloudflare)?)?$/i.test(title || '')
      || (bodyText.length < 1200 && /enable javascript and cookies|checking your browser|sign in to continue|验证后继续|需要验证才能继续|访问过于频繁|登录后查看全文|请在微信客户端打开链接/i.test(bodyText));
    if (blocker) throw new ExtractionError('ACCESS_BLOCKED', 'The response is an access, login, or verification page.', 'Open the requested URL with an authorized browser. Save the visible article HTML, then rerun with --url ORIGINAL_URL --html-file /absolute/path/article.html --out OUTPUT_DIR.');

    let root = null;
    let method = null;
    const wechat = document.querySelector('#js_content, .rich_media_content');
    if (wechat && (cleanText(wechat.textContent).length >= 20 || wechat.querySelector('img'))) {
      root = cleanArticle(wechat.cloneNode(true), resolvedUrl);
      method = 'wechat';
    } else {
      const result = new Readability(document.cloneNode(true), { charThreshold: 120, keepClasses: false }).parse();
      if (result && cleanText(result.textContent).length >= 120) {
        root = document.createElement('div');
        root.innerHTML = result.content;
        cleanArticle(root, resolvedUrl);
        method = 'readability';
        title = result.title || title;
        author = result.byline || author;
        site = result.siteName || site;
        language = result.lang || language;
      } else {
        const candidates = [...document.querySelectorAll('article, main, [role="main"]')]
          .map(node => cleanArticle(node.cloneNode(true), resolvedUrl))
          .filter(node => cleanText(node.textContent).length >= 80)
          .sort((a, b) => cleanText(b.textContent).length - cleanText(a.textContent).length);
        if (candidates[0]) { root = candidates[0]; method = 'semantic'; }
      }
    }

    if (!root && !description) throw new ExtractionError('BODY_UNAVAILABLE', 'No readable article body or metadata description was found.', 'The page may render its content in JavaScript or require access. Use an authorized browser to save the visible article HTML, then pass it with --html-file together with the original --url. Do not reconstruct the article from its title or snippets.');
    const kind = root ? 'article' : 'link_card';
    if (!root) {
      method = 'metadata_only';
      warnings.push('Only page metadata was available. The description is a link-card excerpt, not the full article.');
      root = document.createElement('div');
      const preview = textOnly ? null : meta(document, 'og:image', 'twitter:image', 'twitter:image:src');
      if (preview && httpUrl(preview, resolvedUrl)) {
        const image = document.createElement('img');
        image.setAttribute('src', preview);
        image.setAttribute('alt', title || '链接预览图');
        root.append(image);
      }
    }
    const images = textOnly ? [] : collectImages(root, resolvedUrl);
    const contentText = kind === 'article' ? cleanText(root.textContent) : '';
    const contentMarkdown = kind === 'article' ? toMarkdown(root) : '';
    if (kind === 'article' && !contentText && !images.length) throw new ExtractionError('BODY_UNAVAILABLE', 'The article container had no usable text or images.', 'Retrieve the visible article with an authorized browser and rerun using --html-file.');
    if (kind === 'article' && contentText.length < 120) warnings.push(textOnly
      ? 'The extracted article text is very short. Verify its completeness before writing a summary.'
      : 'The extracted article is very short or primarily images. Verify its completeness before writing a summary.');
    return {
      schema_version: 1, kind, source_url: sourceUrl, resolved_url: resolvedUrl, retrieved_at: retrievedAt,
      title, author, site, language, description,
      extraction: { method, input, text_only: Boolean(textOnly), body_available: kind === 'article', character_count: contentText.length, word_count: wordCount(contentText), warnings },
      content_markdown: contentMarkdown, content_text: contentText, images,
    };
  } finally { dom.window.close(); }
}

function decodeHtml(bytes, contentType = '') {
  const headerCharset = contentType.match(/charset\s*=\s*["']?([^\s;"']+)/i)?.[1];
  const start = bytes.subarray(0, 4096).toString('latin1');
  const metaCharset = start.match(/<meta[^>]+charset\s*=\s*["']?([^\s;"'/>]+)/i)?.[1];
  try { return new TextDecoder(headerCharset || metaCharset || 'utf-8').decode(bytes); }
  catch { return new TextDecoder('utf-8').decode(bytes); }
}

async function fetchHtml(url) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    let resolvedUrl = url;
    let response;
    for (let redirects = 0; redirects <= 5; redirects++) {
      response = await fetch(resolvedUrl, { signal: controller.signal, redirect: 'manual', headers: { 'User-Agent': 'Mozilla/5.0 (compatible; CodexArticleToThread/1.0)', Accept: 'text/html,application/xhtml+xml;q=0.9,*/*;q=0.1' } });
      if ([301, 302, 303, 307, 308].includes(response.status)) {
        const next = httpUrl(response.headers.get('location'), resolvedUrl);
        await response.body?.cancel();
        if (!next || redirects === 5) throw new ExtractionError('REDIRECT_FAILED', 'The response contained an invalid redirect or too many redirects.', 'Open the URL in a browser and use the final article URL or saved HTML.');
        resolvedUrl = next;
        continue;
      }
      break;
    }
    if (!response.ok) {
      await response.body?.cancel();
      throw new ExtractionError('HTTP_ERROR', `The server returned HTTP ${response.status}.`, 'Open the page in an authorized browser. If its article is accessible, save the visible HTML and rerun with --html-file.');
    }
    const contentType = response.headers.get('content-type') || '';
    if (contentType && !/text\/html|application\/xhtml\+xml/i.test(contentType)) {
      await response.body?.cancel();
      throw new ExtractionError('UNSUPPORTED_CONTENT_TYPE', 'The response is not an HTML page.', 'Use an HTML article URL. PDF, video, and document URLs require another extraction workflow.');
    }
    if (Number(response.headers.get('content-length')) > MAX_BYTES) {
      await response.body?.cancel();
      throw new ExtractionError('PAGE_TOO_LARGE', 'The HTML response exceeds the 10 MiB limit.', 'Save just the article HTML locally and use --html-file.');
    }
    const chunks = [];
    let size = 0;
    for await (const chunk of response.body) {
      size += chunk.byteLength;
      if (size > MAX_BYTES) throw new ExtractionError('PAGE_TOO_LARGE', 'The HTML response exceeds the 10 MiB limit.', 'Save just the article HTML locally and use --html-file.');
      chunks.push(chunk);
    }
    return { html: decodeHtml(Buffer.concat(chunks), contentType), resolvedUrl };
  } catch (error) {
    if (error instanceof ExtractionError) throw error;
    throw new ExtractionError('REQUEST_FAILED', controller.signal.aborted ? 'The HTML request timed out after 30 seconds.' : 'The HTML request failed.', 'Check connectivity or retrieve the article in an authorized browser, then rerun with --html-file.');
  } finally { clearTimeout(timer); }
}

function sourceMarkdown(article) {
  const metadata = [`# ${(article.title || '未命名文章').replace(/\s+/g, ' ')}`, '', `来源：${article.source_url}`];
  if (article.author) metadata.push(`作者：${article.author}`);
  metadata.push('');
  if (article.kind === 'link_card') metadata.push('> 仅获取到链接卡片描述，未取得原文正文。以下内容不能当作全文摘要。', '', article.description || '');
  else metadata.push(article.content_markdown);
  return `${metadata.join('\n')}\n`;
}

function parseArgs(args) {
  const options = {};
  for (let i = 0; i < args.length; i++) {
    const flag = args[i];
    if (flag === '--help' || flag === '-h') { options.help = true; continue; }
    if (flag === '--text-only') { options.textOnly = true; continue; }
    if (!['--url', '--out', '--html-file'].includes(flag) || !args[i + 1] || args[i + 1].startsWith('--')) throw new ExtractionError('INVALID_ARGUMENTS', 'An argument is invalid or missing its value.', 'Use --url URL --out OUTPUT_DIR [--html-file SAVED_HTML] [--text-only].');
    options[flag.slice(2)] = args[++i];
  }
  if (!options.help && (!options.url || !options.out)) throw new ExtractionError('INVALID_ARGUMENTS', '--url and --out are required.', 'Use --url URL --out OUTPUT_DIR [--html-file SAVED_HTML] [--text-only].');
  return options;
}

export async function main(args = process.argv.slice(2)) {
  let output;
  try {
    const options = parseArgs(args);
    if (options.help) {
      console.log('Usage: node extract_article.mjs --url URL --out OUTPUT_DIR [--html-file SAVED_HTML] [--text-only]\nRequires Node >=20. Fetches HTML only; never executes page scripts or downloads images.\n--text-only omits image nodes and image metadata while retaining captions and article text.');
      return 0;
    }
    output = path.resolve(options.out);
    await mkdir(output, { recursive: true });
    const sourceUrl = requireUrl(options.url);
    let input;
    if (options['html-file']) {
      const bytes = await readFile(path.resolve(options['html-file']));
      if (bytes.length > MAX_BYTES) throw new ExtractionError('PAGE_TOO_LARGE', 'The HTML file exceeds the 10 MiB limit.', 'Save just the article content as a smaller HTML file.');
      input = { html: decodeHtml(bytes), resolvedUrl: sourceUrl };
    } else input = await fetchHtml(sourceUrl);
    const article = extractHtml(input.html, { sourceUrl, resolvedUrl: input.resolvedUrl, input: options['html-file'] ? 'html_file' : 'url', textOnly: options.textOnly });
    await writeFile(path.join(output, 'article.json'), `${JSON.stringify(article, null, 2)}\n`);
    await writeFile(path.join(output, 'source.md'), sourceMarkdown(article));
    await rm(path.join(output, 'extraction-error.json'), { force: true });
    console.log(`Saved ${path.join(output, 'article.json')} and ${path.join(output, 'source.md')}\nkind=${article.kind}; characters=${article.extraction.character_count}; images=${article.images.length}`);
    return 0;
  } catch (error) {
    const failure = error instanceof ExtractionError ? error : new ExtractionError('EXTRACTION_FAILED', 'The HTML input could not be read or processed.', 'Check the local file path and installed dependencies, then retry.');
    if (output) {
      try {
        await writeFile(path.join(output, 'extraction-error.json'), `${JSON.stringify({ schema_version: 1, error: failure.code, message: failure.message, suggestion: failure.suggestion }, null, 2)}\n`);
      } catch { /* The output directory itself may be unavailable; stderr remains actionable. */ }
    }
    console.error(`Extraction failed: ${failure.code}. ${failure.message}\n${failure.suggestion}`);
    return 1;
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) process.exitCode = await main();
