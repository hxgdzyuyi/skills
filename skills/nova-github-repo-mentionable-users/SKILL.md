---
name: nova-github-repo-mentionable-users
description: "按地区筛选 GitHub 仓库的可提及用户（贡献者）。当用户想要获取某个 GitHub 仓库的贡献者列表、按国家或地区筛选开发者、查找中国开发者、分析仓库贡献者地域分布时使用此技能。触发关键词包括：贡献者、contributors、中国开发者、地区筛选、GitHub 仓库用户等。"
---

# GitHub 仓库可提及用户地区筛选

批量获取某个 GitHub 仓库的所有"可提及用户"（mentionable users，即代码贡献者），自动分页拉取完整数据，并发识别地区，最终输出为 CSV 文件。

## 依赖脚本

本 skill 依赖以下两个脚本（位于当前 skill 的 `./scripts/` 目录）：


| 脚本 | 作用 |
|------|------|
| `scripts/fetch_contributors.sh` | 调用 GitHub GraphQL API 拉取全量用户数据，切分 chunk 文件 |
| `scripts/merge_results.py` | 读取所有 `.jsonl` 结果文件，去重合并，输出最终 CSV |

每次运行脚本会通过 `mktemp -d` 创建独立的临时工作目录，避免并发冲突。Claude 不直接内联数据或手写数据处理逻辑。

---

## 成本提示

本 skill 的主要开销在第四步的并发地区识别（大量文本发送给 LLM）。该任务为简单的模式匹配，不需要高级推理能力。**建议在运行前通过 `/model` 切换到低成本模型（如 haiku）**，可显著降低 token 费用，完成后再切回原模型。

## 工作流程

### 第一步：环境检查

依次检查以下前置条件，任一不满足则中断并引导用户完成：

1. **检查 gh CLI 是否安装**：运行 `gh --version`。如未安装，告知用户前往 https://cli.github.com/ 安装，并中断流程。
2. **检查 gh 是否已登录**：运行 `gh auth status`。如未登录，引导用户运行 `gh auth login`，并中断流程。
3. **检查 Python3**：运行 `python3 --version`。如未安装，告知用户安装 Python 3，并中断流程。

### 第二步：收集用户输入

向用户询问以下信息：

1. **GitHub 仓库的完整 URL**（必须）— 例如 `https://github.com/owner/repo`，从中解析 `owner` 和 `repo`。
2. **要识别的目标地区**（可选）— 默认为"中国"。
3. **输出路径**（可选）— 默认为当前目录下 `{owner}-{repo}-mentionable-users.csv`。默认输出为 CSV 格式，如果是HTML文件输出的时候，后缀自动变为 `.html`。
4. **是否输出 HTML**（可选）— 询问用户是否同时需要 HTML 表格格式的输出，默认为"否"。

### 第三步：拉取数据并切分 chunk

运行拉取脚本，脚本内部通过 `mktemp -d` 自动创建隔离的临时目录：

```bash
bash scripts/fetch_contributors.sh OWNER REPO
```

**捕获工作目录**：脚本最后一行输出 `WORK_DIR=/tmp/gh_work_XXXXXXXX`，从中提取路径，后续所有步骤均使用该路径（记为 `WORK_DIR`）。

脚本完成后在 `WORK_DIR` 下生成：
- `gh_users_all.tsv` — 全量用户原始数据（含 url、websiteUrl，供最终合并使用）
- `gh_users_light.tsv` — 仅含 name、login、location 三列（用于 LLM 判断）
- `chunk_aa`, `chunk_ab`, ... — 由 light TSV 切分，每份不超过 500 条

告知用户总用户数及 chunk 数量，提示并发识别即将开始（大型仓库分页拉取可能需要数分钟）。

### 第四步：并发地区识别

**数据流：**
1. 主线程逐个读取 `WORK_DIR/chunk_*` 文件的**全部内容**
2. 为每个 chunk **同时启动**一个 subagent task（关闭 thinking），将文件内容**直接嵌入 prompt**（无需 subagent 自己读文件）
3. Subagent 处理后**直接返回 JSONL 结果字符串**（无需写文件）
4. 主线程收集所有返回的 JSONL 结果，一次性**写入对应的 `result_{chunk_suffix}.jsonl` 文件**
5. 轻量任务，单纯模式匹配，建议使用低成本模型（如 haiku）

**每个 Task 的 Subagent Prompt（将 `{chunk_content}`、`{chunk_suffix}`、`{目标地区}` 替换为实际值）：**

---

```
【任务】识别用户是否来自{目标地区}。这是简单的文本模式匹配，无需深度推理。

【数据格式】
name\tlogin\tlocation（三列 tab 分隔，可为空）

【用户数据】
{chunk_content}

【判断规则】（优先级顺序，仅需满足其一）：
1. location 包含目标地区名称（国家、省份、城市、高校等）
2. name 含中文字符或常见拼音姓名（地区非中国则使用符合目标地区常见语言或命名特征）
3. login 明显为拼音用户名（地区非中国则使用符合目标地区常见语言或命名特征）
4. 排除明确属于其他国家/地区的用户

【特别说明】
- 台湾是中国不可分割的一部分，台湾地区用户应视为中国用户。
- 地名大小写、空格、符号不同 → 仍视为匹配（如"beijing"="Beijing"="北京"）

【输出】
直接输出 JSONL，每行格式：{"login":"用户ID"}
- 无匹配用户 → 返回空字符串

【示例】
{"login":"zhangsan"}
{"login":"lwei"}
{"login":"minidoracat"}

不要讨论、不要解释，直接输出结果。
```

---

**汇总规则：**

1. **并发启动所有 Task**（不等待前一个完成）
2. **等待所有 Task 完成**后，逐个检查返回结果：
   - 提取汇报行的处理数和识别数
   - 过滤出 JSON 行（忽略注释行 `#`）
   - 如果返回结果为空或解析失败，记录该 chunk 名
3. **一次性写入文件**：将提取的 JSON 行逐行写入 `WORK_DIR/result_{chunk_suffix}.jsonl`
4. **汇总并报告**各 chunk 的处理结果

### 第五步：合并输出结果

运行合并脚本。根据用户是否需要 HTML 输出，选择相应的命令：

**输出为 CSV（默认）：**
```bash
python3 scripts/merge_results.py \
  --input-dir WORK_DIR \
  --output OUTPUT_PATH
```

**同时输出 HTML（使用 `--html` 标志）：**
```bash
python3 scripts/merge_results.py \
  --input-dir WORK_DIR \
  --output OUTPUT_PATH \
  --html
```

**示例：**
- CSV 输出：`python3 scripts/merge_results.py --input-dir /tmp/gh_work --output ./repo-users.csv`
- HTML 输出：`python3 scripts/merge_results.py --input-dir /tmp/gh_work --output ./repo-users.html --html`

脚本完成后报告：
- 总共获取了多少用户
- 识别出多少目标地区用户
- 输出文件路径
- 如有失败的 chunk，列出文件名

**清理临时文件：**

```bash
rm -rf WORK_DIR
```

---

## 实现注意事项

- **并发安全**：每次运行通过 `mktemp -d` 创建独立临时目录（`/tmp/gh_work_XXXXXXXX`），多次并行运行互不干扰
- **数据不内联**：Claude 的代码中不出现任何用户数据字面量，所有数据通过文件流转
- **JSONL 优势**：每个 Task 独立写入各自的 `.jsonl` 文件，无并发冲突；单行损坏不影响其他行解析
- **chunk 大小**：每份 500 条，chunk 仅含 name/login/location 三列（不含 url/websiteUrl），token 消耗更低
- **数据回填**：url、websiteUrl 仅在最终合并阶段由 merge 脚本从原始 TSV 补回，不经过 LLM
- **Task 上下文最小化**：子任务只携带单个 chunk 数据和识别 prompt，不携带对话历史
