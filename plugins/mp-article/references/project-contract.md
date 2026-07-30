# mp-article Hugo 工程契约

## 目录

标准工程必须包含：

```text
.gitignore
AGENTS.md
hugo.toml
archetypes/wechat.html
content/_index.md
layouts/wechat/baseof.html
layouts/wechat/single.html
layouts/wechat/home.html
layouts/partials/wechat/copy-button.html
assets/css/wechat-preview.css
assets/css/mp-article-index.css
assets/js/wechat-copy.js
static/static/weui.min.css
static/static/tencent_portfolio_light.mnicjuz14bbf866e.css
```

文章使用 Hugo Leaf Bundle：

```text
content/<slug>/
├── index.html
└── assets/
```

`content/_index.md` 提供 Hugo Home 页面。根级 Leaf Bundle 的 Front Matter 使用 `type: wechat`，自动匹配 `layouts/wechat/single.html`；文章文件路径和 URL 均为 `<slug>` 根级结构，不含 `/wechat/`。

## Codex 工程说明

项目根目录必须包含 `AGENTS.md`，并用 `mp-article:begin` 和 `mp-article:end` 注释标记插件说明。

- 新工程直接从模板创建该文件。
- 已有 `AGENTS.md` 时保留原内容，在文件末尾追加插件说明。
- 已经包含完整标记时不重复追加。
- 只有一个标记或文件不是 UTF-8 时视为冲突并停止。

## Git 忽略规则

项目根目录必须包含最小化的 `.gitignore`，仅覆盖 Hugo 生成物和常见本地元数据：

```gitignore
/public/
/resources/_gen/
.hugo_build.lock
.DS_Store
```

新工程直接创建；已有 `.gitignore` 时保留原内容并在末尾追加带标记的规则块。完整标记已存在时不重复追加，标记残缺或文件不是 UTF-8 时停止。

## 配置标记

`hugo.toml` 必须包含：

```toml
locale = "zh-CN"

[params.mpArticle]
enabled = true
schemaVersion = 1

[security]
allowContent = ['^text/html$']
```

- 工程要求 Hugo v0.162.0 或更高版本。
- 使用顶层 `locale`，不使用 Hugo v0.158.0 起弃用的 `languageCode`。
- `security.allowContent` 只显式允许 `text/html`，以便构建 `index.html` 文章正文。
- `disableKinds` 不得包含 `home`，首页负责列出所有 `type: wechat` 文章。
- 已有顶层 `languageCode` 时保留原值并迁移为 `locale`；如果 `locale` 已存在，则移除旧键。
- 已有 `[security]` 但缺少 `allowContent` 时允许补充。
- 已有 `allowContent` 但未精确允许 `^text/html$` 时视为安全策略冲突，不自动覆盖。
- 旧版配置禁用 `home` 时允许从 `disableKinds` 中移除。
- 已有配置缺少 `[params.mpArticle]` 时允许在文件末尾追加。块存在但 `enabled` 或 `schemaVersion` 不匹配时视为冲突。

## 初始化安全

- 空目录允许调用 `hugo new site`，随后安装模板。
- `.git` 和 `.DS_Store` 不影响空目录判断。
- 非空目录先预检所有目标文件，再执行任何写入。
- 目标文件不存在时复制。
- 目标文件与模板字节一致时跳过。
- 同名文件内容不同时报告冲突并停止。
- `AGENTS.md` 是例外：已有文件保留并在末尾追加带标记的插件说明。
- `.gitignore` 是例外：已有文件保留并在末尾追加最小 Hugo 忽略规则。
- `hugo.toml` 是例外：只执行上述可判定的配置迁移；安全策略冲突时停止。
- `layouts/wechat/baseof.html` 仅在差异恰好是旧版 `.Site.LanguageCode` 写法时升级为 `.Site.Language.Locale`。
- 不覆盖、不重命名、不自动备份用户文件。
- `config.toml`、`config.yaml` 或 `config.json` 存在而 `hugo.toml` 不存在时停止，避免改变已有配置选择。

## 内容与交付

- 根级文章通过 Front Matter 的 `type: wechat` 选择 `layouts/wechat/single.html`。
- `layouts/wechat/home.html` 从 `.Site.RegularPages` 筛选 `type: wechat` 文章。
- `index.html` 使用 YAML Front Matter，正文保留原始 HTML。
- `single.html` 使用 `.RawContent | safeHTML`。
- Bundle 图片使用 `assets/<file>` 相对路径。
- Layout 负责发布 Page Resources、加载预览 CSS 和复制脚本。
- 单篇文章使用 `image2-mp` 同等的微信 DOM 层级、body class、WeUI、腾讯公众号样式和 `578px` 正文画布。
- 微信 body class 和右上角复制工具只用于单篇文章；首页列表不显示复制工具。
- `wechat-preview.css` 从 `image2-mp` 的 `app.css` 提炼；WeUI 和腾讯公众号样式作为项目本地静态资源加载。
- 首页列表样式独立放在 `mp-article-index.css`，避免改变单篇文章预览环境。
- 预览层只使用项目内本地 CSS 和 JavaScript；项目自有 CSS 通过 Hugo Pipes 加载。
- 不引入 Tailwind CSS、PostCSS、npm 构建链或外部 CSS CDN。
- 复制脚本只序列化 `#js_content` 的子节点，不复制页面外壳。
