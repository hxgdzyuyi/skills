# mp-article Hugo 工程契约

## 目录

标准工程必须包含：

```text
hugo.toml
archetypes/wechat.html
content/wechat/_index.md
layouts/wechat/baseof.html
layouts/wechat/single.html
layouts/wechat/list.html
layouts/partials/wechat/copy-button.html
assets/css/wechat-preview.css
assets/js/wechat-copy.js
```

文章使用 Hugo Leaf Bundle：

```text
content/wechat/<slug>/
├── index.html
└── assets/
```

## 配置标记

`hugo.toml` 必须包含：

```toml
[params.mpArticle]
enabled = true
schemaVersion = 1
```

已有配置缺少该块时允许在文件末尾追加。块存在但 `enabled` 或 `schemaVersion` 不匹配时视为冲突。

## 初始化安全

- 空目录允许调用 `hugo new site`，随后安装模板。
- `.git` 和 `.DS_Store` 不影响空目录判断。
- 非空目录先预检所有目标文件，再执行任何写入。
- 目标文件不存在时复制。
- 目标文件与模板字节一致时跳过。
- 同名文件内容不同时报告冲突并停止。
- 不覆盖、不重命名、不自动备份用户文件。
- `config.toml`、`config.yaml` 或 `config.json` 存在而 `hugo.toml` 不存在时停止，避免改变已有配置选择。

## 内容与交付

- `content/wechat` 的 Section 自动选择 `layouts/wechat`。
- `index.html` 使用 YAML Front Matter，正文保留原始 HTML。
- `single.html` 使用 `.RawContent | safeHTML`。
- Bundle 图片使用 `assets/<file>` 相对路径。
- Layout 负责发布 Page Resources、加载预览 CSS 和复制脚本。
- 复制脚本只序列化 `#js_content` 的子节点，不复制页面外壳。
