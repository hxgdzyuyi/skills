<!-- mp-article:begin -->
## mp-article 公众号文章工程

本工程使用 Codex `mp-article` 插件维护公众号文章。

- 初始化、检查、新建、编辑和预览工程时使用 `mp-article:mp-article-project`。
- 生成或修改公众号正文时使用 `mp-article:mp-rich-html` 的工程模式。
- 文章放在 `content/<slug>/index.html`，素材放在同级 `assets/`，Front Matter 使用 `type: wechat`。
- 文章列表发布到 `/`，文章详情发布到 `/<slug>/`；文件路径和 URL 都不带 `/wechat/` 前缀。
- 正文必须使用公众号兼容的全内联 HTML，不依赖外部 CSS、JavaScript、`id` 或 `class`。
- 预览层只使用项目内原生 CSS/JavaScript 和 Hugo Pipes，不引入 Tailwind CSS、PostCSS、npm 构建链或外部 CSS CDN。
- 文章预览层复刻 `image2-mp` 的微信 DOM、WeUI、腾讯公众号样式和 `578px` 正文画布，不自行简化成通用卡片页面。
- 微信 body class 和复制工具只用于单篇文章，首页列表不显示复制按钮。
- 交付前运行 Hugo 模式 HTML 检查，并通过 Hugo 预览页复制 `#js_content`。
<!-- mp-article:end -->
