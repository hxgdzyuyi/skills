# hxgdzyuyi Skills

## 1. Codex 公众号文章

`mp-article` 是面向微信公众号文章生产与管理的 Codex 插件。它既可以把草稿或 Markdown 整理成公众号编辑器可直接粘贴的全内联 HTML，也可以初始化和维护完整的 Hugo 公众号文章工程。

<img src="plugins/mp-article/assets/icon.png" width="128" alt="公众号文章插件图标">

插件提供两个可独立使用的 Skill：

- `mp-rich-html`：在任意已有项目中新增或编辑公众号兼容 HTML，不要求使用 Hugo。
- `mp-article-project`：初始化、检查和管理 Hugo 公众号文章工程，支持文章 Bundle、本地预览和复制交付。

工程模式遵循 Hugo 原生目录体系：

```text
content/<slug>/
├── index.html
└── assets/
```

文章 Front Matter 使用 `type: wechat` 匹配公众号 Layout。Hugo 首页 `/` 展示公众号文章列表，文章文件路径和访问地址都不带 `/wechat/` 前缀。

初始化时还会在工程根目录创建 `AGENTS.md` 和最小化 `.gitignore`；如果文件已经存在，则保留原内容并在末尾追加 `mp-article` 插件说明或 Hugo 忽略规则。

工程要求 Hugo v0.162.0 或更高版本。生成的配置使用 `locale`，并只为 `text/html` 显式放行内容构建，兼容新版 Hugo 对原始 HTML 正文的默认安全限制。预览层使用项目内原生 CSS/JavaScript 和 Hugo Pipes，不需要 Tailwind CSS、PostCSS 或 npm。

文章正文使用公众号兼容的全内联样式。单篇预览复刻 `image2-mp` 的微信 DOM、WeUI、腾讯公众号样式和 `578px` 正文画布，并通过复制工具只提取 `#js_content`，同时尝试内联计算样式和本地图片。

### 安装

本仓库提供 Codex 本地插件市场描述文件：

```text
.agents/plugins/marketplace.json
```

添加或启用该 marketplace 后安装 `mp-article`。插件源码位于：

```text
plugins/mp-article
```

### 使用示例

```text
把这篇 Markdown 整理成公众号可直接粘贴的富文本 HTML。
初始化当前目录为公众号文章 Hugo 工程。
在公众号工程中新增一篇文章，并启动本地预览。
编辑已有文章，保留素材和 Front Matter。
```

详细说明：

- [公众号富文本 HTML](plugins/mp-article/skills/mp-rich-html/SKILL.md)
- [公众号文章工程](plugins/mp-article/skills/mp-article-project/SKILL.md)

## 2. 其他 Codex 插件

### 文章轮播卡片

`article-card-carousel` 可以把文章、笔记或草稿整理成有序 SVG/PNG 图文卡片，包含模板、预览检查和渲染流程。详见 [文章轮播卡片 Skill](plugins/article-card-carousel/skills/article-card-carousel/SKILL.md)。

## 3. Repository Introduction

This repository contains skills for Claude Code and plugins for Codex.

### Installation

#### Claude Code

1. Register the repository as a plugin marketplace:

```
/plugin marketplace add hxgdzyuyi/skills
```

2. To install a skill, run:

```
/plugin install <skill-name>@hxgdzyuyi-skills
```

For example:

```
/plugin install nova-github-repo-mentionable-users@hxgdzyuyi-skills
```

#### Codex

Codex plugins are exposed through the local marketplace descriptor:

```
.agents/plugins/marketplace.json
```

The primary Codex plugin is `mp-article`:

```text
plugins/mp-article
```

The marketplace also includes `article-card-carousel` and other local plugins.

### Skills

| Name | Description | Documentation |
|------|-------------|---------------|
| nova-github-repo-mentionable-users | 导出 Github 项目上贡献过代码的中国人（或者其他地区的人）。 | [SKILL.md](skills/nova-github-repo-mentionable-users/SKILL.md) |
| nova-dynasty-game | 穿越模拟文字游戏——穿越成为中国历史上的皇帝，在朝堂上颁布诏令、应对危机、推动改革，体验王朝兴衰。 | [SKILL.md](skills/nova-dynasty-game/SKILL.md) |
| magneto-mortal-cultivation-story | 约100次互动的“万磁王穿越到《凡人修仙传》”三幕小说故事，支持可变大纲与连续性记录。 | [SKILL.md](skills/magneto-mortal-cultivation-story/SKILL.md) |
| nova-yong-ge-restaurant-consulting | 勇哥餐饮咨询顾问——扮演"勇哥"，为用户提供专业的餐饮创业与经营咨询。 | [SKILL.md](skills/nova-yong-ge-restaurant-consulting/SKILL.md) |
| network-resume | 当用户输入 /network-resume 时触发，输出一句固定话术用于在网络中断后继续之前的任务。 | [SKILL.md](skills/network-resume/SKILL.md) |
| explain-code | 根据用户传入的源码路径或 glob 生成源码解析文档，并汇总文件功能与依赖关系。 | [SKILL.md](skills/explain-code/SKILL.md) |
| refactor-hotspots | 分析 Git 仓库最近频繁被修改的"热点文件"并给出重构建议（DRY、SRP、耦合等视角）。手动调用触发（/refactor-hotspots） | [SKILL.md](skills/refactor-hotspots/SKILL.md) |
| render-plan | 润色和完善 docs/plans/ 下的计划文档，按标准层面结构整理内容。手动调用触发（/render-plan） | [SKILL.md](skills/render-plan/SKILL.md) |
| run-plan | 落地 docs/plans/ 下的计划文档到当前项目。传入计划文件路径作为参数即开始执行；不传参数则列出所有可用计划供用户选择，手动触发。 | [SKILL.md](skills/run-plan/SKILL.md) |

### Codex Plugins

| Name | Display Name | Description | Documentation |
|------|--------------|-------------|---------------|
| mp-article | 公众号文章 | 生成公众号兼容富文本，并初始化和管理可预览、可复制交付的 Hugo 公众号文章工程。 | [SKILL.md](plugins/mp-article/skills/mp-article-project/SKILL.md) |
| article-card-carousel | 文章轮播卡片 | 将文章或笔记整理成 SVG/PNG 图文卡片。 | [SKILL.md](plugins/article-card-carousel/skills/article-card-carousel/SKILL.md) |
