---
name: mp-rich-html
description: 把文章/草稿/主题整理成微信公众号编辑器可直接粘贴的兼容富文本（全内联样式 HTML）。当用户要"公众号排版/微信富文本/公众号样式"，或要把 markdown 转成公众号文章时使用。也可手动调用（/mp-rich-html）。
---

# WeChat Rich Text

生成可直接粘贴进**微信公众号编辑器**的富文本 HTML。产物是一个自包含的 `.html` 文件：用浏览器打开即所见即所得，全选复制后粘到公众号后台即保留排版。

## 公众号 HTML 约束

实测真实推文正文（`.rich_media_content`）后，归纳出以下硬约束——公众号真会过滤，违反就丢样式。

- 公众号**不支持外部 CSS/JS**，会丢弃 `<style>`、`<link>`、`<script>`，也不支持 `@media`、`@font-face`、`@keyframes` 等 at-rule（没有样式表环境）。**所有要保留的样式必须写成元素上的内联 `style`**。
- `id` 会被直接删除；`class` 会保留但因无 CSS 环境而完全无效——不要把任何视觉效果寄托在 `class` 上。
- 交互/可执行类标签 `<iframe>`、`<form>`、`<input>`、`<object>`、`<embed>` 会被过滤，不要使用。
- 图片 `src` 必须是 **HTTPS 绝对 URL**（公众号素材库 URL / 可公开访问的外链 / `data:image/...;base64,` 内联），不得编造。粘贴后公众号会重新处理 `<img>`（换成自家 CDN、补 `data-ratio` 等），外链/base64 图多半不显示，需手动上传素材库。

> 实测补充：除以上几项外，公众号**几乎保留全部内联 CSS**——`transform`、`float`、`position`、`grid`、`background-image`、`flex`、`box-shadow`、`opacity` 在真实推文里都能正常用（秀米/135 等模板大量使用）。

## SVG（本 skill 不生成，但需了解边界）

实测一篇真实「SVG 动效推文」（正文含 85 个 `<svg>`、63 个 `<foreignObject>`）后明确：

- 公众号**完整支持内联 `<svg>`**——「SVG 动效/互动长图」推文就是这么实现的。实测可用：`<foreignObject>`（在 SVG 内嵌 HTML）、`<g>`/`<text>`/`<tspan>`、`viewBox`、`preserveAspectRatio`、百分比 `width`（可 >100%，配合外层 `overflow-x:scroll` 的 `<section>` 实现横向滚动）。
- **SMIL 动画/交互可用**：`<animate>`、`<animateTransform>`、`<set>`，支持 `begin="click"` 点击触发、`dur`、`fill="freeze"`、`restart="never"`。这是公众号里唯一能做动画/交互的途径（CSS `@keyframes` 因 `<style>` 被丢弃而无效）。
- SVG 推文里的图片都画成 `<svg>` 的 `background-image:url(公众号图床地址)`，并非 `<img>`。
- **但本 skill 不生成 SVG**：互动长图依赖绝对坐标、嵌套 `<svg>`/`<foreignObject>`、手工调校的动画 `values`，且图片须先上传到公众号图床——只能用秀米/135 等专门 SVG 工具制作，无法用「写 HTML → 浏览器复制粘贴」这套流程稳定手写。
- 本 skill 只产出**普通语义 HTML 的干净阅读排版**。用户若想要的是 SVG 动效/互动推文，应明确告知其属另一套工作流（需专门工具），本 skill 不覆盖。简单静态内联 `<svg>`（图标、装饰形状）粘贴可保留，但非必要不引入。

## 默认风格变量

用户没特别要求时，用这套「干净极简」风格；用户给了品牌色/偏好就替换对应值：

| 变量 | 默认值 | 用途 |
|------|--------|------|
| 正文字号 | `15px` | `<p>` 等正文 |
| 行高 | `1.75` | 正文 `line-height` |
| 字间距 | `0.5px` | `letter-spacing` |
| 正文色 | `#3f3f3f` | 正文文字 |
| 标题色 | `#1a1a1a` | 标题/重点 |
| 次要色 | `#999` | 图注、署名、副标题 |
| 主色 | `#07c160` | 标题色条、强调、提示框 |
| 分隔线色 | `#ebebeb` | 分隔/边框 |

## 工作流程

### 1. 收集输入

- 内容来源：用户给的 markdown / 纯文本 / 文章草稿，或仅一个主题。
- 只给了主题时，先与用户确认是否要 Claude 起草正文，再继续。
- 配图：逐张确认 HTTPS URL。**没有 URL 就保留占位说明并提示用户补充，绝不编造链接。**

### 2. 确认风格

采用默认风格变量。如用户给了品牌色或排版偏好（字号、是否要色块标题等），相应调整。

### 3. 生成 HTML

- 按上面的约束和风格变量逐块写组件（标题、小标题、正文、强调、列表、引用、分隔线、配图+图注、提示框、表格、链接、署名），每个组件的样式都内联到元素上。
- 最外层一个 `<section>` 设基础排版（`font-size`、`line-height`、`color`、`letter-spacing`、`word-break:break-word`）。
- 逐块组装内容，每个需要保留的样式都**内联**写在元素上。
- 块与块之间靠元素自身的 `margin` 拉开间距，**不要用空 `<p>` 撑空白**。
- 图片统一加 `display:block;width:100%;max-width:100%;height:auto;box-sizing:border-box;`。

### 4. 写出文件

写到 `./wechat-output/{slug}.html`（`{slug}` 由标题生成，纯英文/数字/连字符；目录不存在就创建）。

文件结构如下——`<body>` 内**只放**那段可粘贴的 `<section>`，`<head>` 不放任何会影响正文的样式：

```html
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>{文章标题}</title>
</head>
<body style="margin:0;padding:24px 12px;background-color:#f2f2f2;">
<section style="max-width:677px;margin:0 auto;background-color:#ffffff;padding:24px 18px;font-size:15px;line-height:1.75;color:#3f3f3f;letter-spacing:0.5px;word-break:break-word;">
  <!-- 文章正文：标题、段落、图片等组件 -->
</section>
</body>
</html>
```

> `<body>` 的灰底只是浏览器预览效果，复制时不会带入；真正粘贴的内容是那段 `<section>`。

### 5. 交付说明

把文件路径告诉用户，并附上操作步骤：

1. 用浏览器打开生成的 `.html` 预览效果。
2. 在页面上**全选正文**（点进白色卡片内 → `Cmd/Ctrl+A`）→ `Cmd/Ctrl+C`。
3. 粘贴进微信公众号后台编辑器。
4. 图片若是外链或 base64，公众号通常**不会自动转存**——需逐张上传到素材库后替换 `src`。

## 生成后自查清单

- [ ] 没有 `<style>`、`<script>`、`class=`、`id=`
- [ ] 所有样式都在元素的 `style=` 内联属性里
- [ ] 每个 `<img src>` 都是 `https://` 或 `data:`，且有 `display:block;max-width:100%;height:auto;`
- [ ] 颜色用十六进制，字号用 `px`
- [ ] 表格设了 `border-collapse:collapse`，单元格都有 `border` 和 `padding`
- [ ] 相邻块都显式设了 `margin`，没有靠空段落撑高

## 已知坑

- 外链图片粘贴后多数不显示、也不会自动转存，务必提醒用户手动上传替换。
- 行内元素（`span`）的 `background-color` 偶尔会被裁剪；重要底色尽量放在 `section`/`p` 上更稳。
- 不要依赖 `margin` 折叠；相邻块各自显式给 `margin`。
- `<a>` 指向 `mp.weixin.qq.com` 的公众号文章链接可用（会渲染成卡片）；指向其他站点的外链在正文里通常不可点击，`<a>` 多作展示用途。
- 公众号粘贴后会重排 `<img>`、给元素补 `white-space`/`box-sizing` 等属性，预览与最终效果可能有细微差异，以公众号后台预览为准。
