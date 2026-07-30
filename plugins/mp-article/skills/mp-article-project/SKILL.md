---
name: mp-article-project
description: 初始化、检查和管理遵循 Hugo 目录体系的微信公众号文章工程，并在工程内创建、编辑、预览和复制交付文章。用户要求建立公众号文章项目、工程化维护多篇公众号文章、接入现有 Hugo 项目，或在标准 mp-article 工程中新增和编辑文章时使用。
---

# 公众号文章工程

管理 Hugo 公众号文章工程。文章正文必须遵循同插件的 `mp-rich-html` Skill。

## 路由边界

- 用户显式调用 `mp-rich-html` 时，不触发工程初始化。
- 用户只要求生成单篇公众号 HTML，且当前目录不是标准工程时，交给 `mp-rich-html` 独立模式。
- 用户要求初始化、工程化管理、接入 Hugo，或当前目录已经是标准工程时，使用本 Skill。
- 不自动安装 Hugo，不覆盖冲突文件，不登录或发布到公众号。

## 工程入口

插件根目录下的脚本提供稳定接口：

```bash
python3 <plugin-root>/scripts/mp_article_project.py doctor --root <project>
python3 <plugin-root>/scripts/mp_article_project.py init --root <project>
python3 <plugin-root>/scripts/mp_article_project.py new --root <project> --slug <slug> --title <title>
```

退出码：

- `0`：成功或工程完整。
- `1`：缺失文件、参数错误、文章已存在或文件冲突。
- `2`：没有找到 Hugo。

## 初始化或接入

1. 确定用户指定的项目根目录，默认使用当前目录。
2. 运行 `doctor`。
3. 退出码为 `2` 时，向用户报告检测结果和脚本给出的安装方式，停止初始化。
4. 退出码为 `1` 且用户确实要求工程化管理时，运行 `init`。
5. `init` 报告冲突时停止，不自行覆盖、重命名或备份。
6. 再运行 `doctor`，确认工程契约完整。

空目录由 Hugo CLI 创建基础站点。非空目录只增量安装缺失文件。现有 `hugo.toml` 只允许追加缺失的 `[params.mpArticle]` 标记；已存在但值冲突时停止。

## 新建文章

1. 将标题转成小写英文、数字和连字符组成的 slug；无法可靠翻译时向用户确认 slug。
2. 运行 `new` 创建 `content/wechat/{slug}/index.html` 和同级 `assets/`。
3. 读取并遵循 `../mp-rich-html/SKILL.md`，使用工程模式填充正文。
4. 图片放进当前文章的 `assets/`，正文使用 `assets/{file}`。
5. 运行 `lint_mp_html.py <article> --mode hugo`，修复全部错误。

## 编辑文章

1. 根据用户给出的 slug、标题或文件路径定位 `content/wechat/{slug}/index.html`。
2. 保留 Front Matter、未涉及正文和现有资源。
3. 读取并遵循 `../mp-rich-html/SKILL.md`，使用工程模式执行修改。
4. 运行 Hugo 模式静态检查。

## 预览和交付

在项目根目录运行：

```bash
hugo server --config hugo.toml -D
```

需要生成可交付的静态站点时运行：

```bash
hugo --config hugo.toml -D
```

构建结果由 Hugo 写入标准 `public/` 目录。该命令只构建静态页面，不登录或发布到公众号。

预览页面中的标题、日期、复制按钮和灰色页面背景属于预览外壳。只有 `#js_content` 的内部内容会进入剪贴板。

交付时说明：

1. 打开目标文章页面。
2. 点击“复制公众号正文”。
3. 粘贴到微信公众号后台。
4. 检查脚本报告的图片转换失败项。
5. 在公众号素材库重新上传和替换需要托管的图片。

## 工程约束

需要详细判断时读取插件根目录的 `references/project-contract.md`。不要在生成的项目中创建插件专用状态目录；工程状态只由 Hugo 原生结构和 `hugo.toml` 参数表达。
