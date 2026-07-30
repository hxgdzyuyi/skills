---
name: mp-rich-html
description: 把文章、草稿、Markdown 或主题整理成微信公众号编辑器可直接粘贴的全内联富文本 HTML，也可在已有文件中编辑公众号正文。用户要求公众号排版、微信富文本、公众号 HTML、把 Markdown 转成公众号文章，或手动调用 /mp-rich-html 时使用。既支持独立 HTML 文件，也支持 mp-article Hugo 工程中的文章 Bundle。
---

# 公众号富文本 HTML

生成或编辑普通语义 HTML 的公众号正文。不要初始化 Hugo；只有 `mp-article-project` 负责工程管理。

## 选择输出模式

先根据目标选择模式：

- 独立模式：用户直接调用且没有指定标准 Hugo 文章目标。写入 `./wechat-output/{slug}.html`。
- 工程模式：由 `mp-article-project` 调用，或目标是 `content/{slug}/index.html` 且 Front Matter 为 `type: wechat`。直接编辑该文件。
- 用户明确指定现有 HTML 文件时，原地编辑，不另建输出。

显式调用本 Skill 时，不因当前目录缺少 Hugo 而初始化或改造工程。

## 微信兼容硬约束

- 正文不得依赖外部 CSS 或 JavaScript。不得包含 `<style>`、`<link>`、`<script>` 或 CSS at-rule。
- 所有需要保留的视觉样式都写在元素的 `style` 属性中。
- 正文不得包含 `id` 或 `class` 属性。
- 不使用 `<div>`。块级容器使用 `<section>` 或 `<p>`。
- 不使用 `<iframe>`、`<form>`、`<input>`、`<object>`、`<embed>`。
- 不生成 SVG 动效或互动推文。用户需要互动 SVG 时说明它属于专门工具工作流。
- 块间距使用显式 `margin`，不用空段落撑高。
- 图片统一包含 `display:block;width:100%;max-width:100%;height:auto;box-sizing:border-box;`。
- 表格使用 `border-collapse:collapse`，每个单元格显式设置 `border` 和 `padding`。
- 颜色优先使用十六进制，字号使用 `px`。

## 图片规则

独立模式仅允许：

- 已确认存在的 `https://` URL。
- `data:image/...` URL。
- 没有可用地址时保留清晰的文字占位，不编造 URL。

工程模式额外允许 `assets/{file}` 相对路径。文件必须存在于当前文章 Bundle 的 `assets/` 目录；复制页面会尝试将其转换为 Base64。不要使用 `../` 或项目根绝对路径。

## Flex 和多列

Flex 只用于简单单行对齐：

- 父级可使用 `display:-webkit-flex;display:flex;justify-content:space-between;align-items:stretch;`。
- 两列子项使用明确的 `width:48%;max-width:48%;box-sizing:border-box;`。
- 禁止 `flex:`、`flex-basis`、`flex-wrap`、`gap` 和用 `calc()` 计算列宽。
- 多行卡片拆成多个单行 Flex 容器。
- 徽章和居中提示优先使用 `text-align:center` 与 `display:inline-block`。

## 默认样式

用户没有指定品牌风格时使用：

| 项目 | 默认值 |
|------|--------|
| 正文字号 | `15px` |
| 行高 | `1.75` |
| 字间距 | `0.5px` |
| 正文色 | `#3f3f3f` |
| 标题色 | `#1a1a1a` |
| 次要色 | `#999999` |
| 主色 | `#07c160` |
| 分隔线 | `#ebebeb` |

用户给出品牌色、字号或组件偏好时替换对应变量，不改变兼容约束。

## 工作流程

1. 读取用户给出的草稿、Markdown、纯文本或现有文章。
2. 只有主题而没有正文时，先确认是否需要起草正文。
3. 确定输出模式、目标文件、文章标题和图片来源。
4. 新建时组织标题、小标题、正文、强调、列表、引用、图片、图注、提示框、表格和署名。
5. 编辑时保留 Front Matter、未涉及正文、现有素材路径和用户没有要求改变的风格。
6. 写入目标后运行插件根目录的 `scripts/lint_mp_html.py`。
7. 修复所有错误；警告需要在交付说明中告知用户。

## 独立模式文件

生成完整 HTML：

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{文章标题}</title>
</head>
<body style="margin:0;padding:24px 12px;background-color:#f2f2f2;">
<section style="max-width:677px;margin:0 auto;padding:24px 18px;background-color:#ffffff;color:#3f3f3f;font-size:15px;line-height:1.75;letter-spacing:0.5px;word-break:break-word;">
  <!-- 公众号正文 -->
</section>
</body>
</html>
```

检查命令：

```bash
python3 <plugin-root>/scripts/lint_mp_html.py ./wechat-output/{slug}.html --mode standalone
```

## 工程模式文件

保留标准 Front Matter，正文只放可复制片段：

```html
---
title: "文章标题"
type: wechat
date: 2026-07-30T00:00:00+08:00
description: ""
cover: ""
---
<section style="color:#3f3f3f;font-size:15px;line-height:1.75;letter-spacing:0.5px;word-break:break-word;">
  <!-- 公众号正文 -->
</section>
```

检查命令：

```bash
python3 <plugin-root>/scripts/lint_mp_html.py content/{slug}/index.html --mode hugo
```

## 交付

独立模式告诉用户：

1. 用浏览器打开文件。
2. 在白色正文区域全选并复制。
3. 粘贴到微信公众号后台编辑器。

工程模式告诉用户：

1. 使用 `hugo server --config hugo.toml -D` 启动预览。
2. 打开文章页面并点击“复制公众号正文”。
3. 粘贴到公众号后台。

两种模式都提醒：外链和 Base64 图片通常仍需在公众号素材库中上传并替换，以公众号后台最终预览为准。

## 自查

- 没有禁止标签、`id` 或 `class`。
- 所有正文视觉样式均已内联。
- 图片来源符合当前模式且具有完整响应式样式。
- 多列没有使用不稳定 Flex 写法。
- Hugo 模式没有完整文档外壳，独立模式具有完整文档外壳。
- 静态检查器没有报告错误。
