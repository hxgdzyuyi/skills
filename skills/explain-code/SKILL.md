---
name: explain-code
description: "根据用户传入的源码路径或 glob 生成简洁的中文源码解析文档。适用于用户要求解释、阅读、理解、总结或为某个源码目录生成文档的场景，尤其是类似“解释 packages/agent/src/**/*”或“为某个目录生成源码解析文档”的请求。"
disable-model-invocation: true
---

# Explain Code

为用户传入的源码路径生成面向快速阅读的中文 Markdown 解析文档。每个源码文件对应一个文档文件，并在对话中汇总每个文件的功能和简单依赖关系。

## 工作流程

1. **确定目标文件**
   - 接受一个或多个用户传入的路径或 glob。
   - 优先运行本 skill 的 `scripts/plan_code_explanations.py`，列出源码文件和对应输出路径：
     ```bash
     python3 /path/to/skill/scripts/plan_code_explanations.py 'packages/agent/src/**/*'
     ```
   - 如果脚本不可用，使用 `rg --files` 结合 shell glob 找出真实文件。
   - 跳过通常不是手写源码的目录和文件：`.git`、`node_modules`、`dist`、`build`、`coverage`、`.next`、`.turbo`、`target`、`vendor`、生成的 lock 文件、二进制文件、图片、压缩包和 minified bundle。
   - 跳过 `.gitignore` 命中的文件。

2. **结合上下文阅读代码**
   - 默认完整阅读每个目标文件；如果文件很大，先用 `rg`、符号列表、imports 和关键片段了解结构。
   - 必要时阅读相邻文件、被 import 的文件或调用方，以理解主要行为，但生成文档时仍聚焦目标文件本身。
   - 优先依据结构化线索判断：imports/exports、公开 API、类/函数名、路由注册、测试、类型定义和调用点。

3. **为每个源码文件写一份 Markdown**
   - 文档写到 `docs/code_explanations/` 下。
   - 保留源码路径结构。例如：
     - `packages/agent/src/index.ts`
     - `docs/code_explanations/packages/agent/src/index.ts.md`
   - 尽量使用 `plan_code_explanations.py` 输出的文档路径。
   - 按需创建父目录。

4. **在对话中汇总**
   - 写完后告诉用户生成了哪些文档。
   - 用简洁列表描述每个文件的功能和简单依赖关系。

## Document Format

1. 主要是帮助我快速读懂源码
2. 要到一个 overview 模块，快速说明这个文件的功能
3. 后续解释功能，必要的时候可以引用代码，挑选重要的说，不要太冗长

## 最终回复格式

生成完成后，用中文回复，并包含：

```markdown
已生成源码解析文档：
- `<文档路径>`：`<源码路径>`

文件功能和依赖关系：
- `<源码路径>`：<一句话功能>；依赖 <关键依赖>。
```
