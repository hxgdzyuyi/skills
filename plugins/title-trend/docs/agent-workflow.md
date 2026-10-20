# Agent 提供 LLM 的工作流

模型由 Codex 等当前 Agent 环境提供。Python 服务不调用任何模型 API，不读取客户端模型登录凭证，也不要求配置 Chat Completions endpoint。标准 Skill 指导 Agent 通过 MCP 组织流程，任意具备工具调用能力的 Agent 都可使用；不要求 MCP Sampling。

一次用户请求，通常包含三次工具调用：

```
原标题 → prepare_title：jieba 分词参考
       → 当前 Agent：理解主题并选择候选短语
       → analyze_title：真实查询、缓存、Python 评分
       → 当前 Agent：基于返回数据撰写分析与标题建议
       → complete_report：校验建议并合并完整报告
```

## 1. 准备候选词

`prepare_title(title, market?)` 不访问 DataForSEO，不读取凭证，不创建关键词缓存。返回原标题、明确市场、`segmentation_candidates`、候选词 schema 和下一步指引。使用 UTF-8 自定义 jieba 词典时保持相同配置。

## 2. 查询与评分

当前 Agent 选词后调用：

```json
{
  "title": "用 Python 自动化办公，如何减少重复工作？",
  "market": "CN",
  "selection": {
    "topic": "Python自动化办公",
    "candidates": [
      {
        "keyword": "Python 自动化办公",
        "anchors": ["Python", "自动化"],
        "relevance": "原标题工具与用途"
      }
    ]
  }
}
```

候选短语 1–5 个，唯一且直接关联原标题。anchors 每词 1–3 个，须同时在标题与短语中出现。当前校验仅允许原标题的词或重组，拒绝未提供的新实体和主题词；不会把有原文锚点但夹带无关热词的短语当作合格。结构错误或夹带 score/weights 时，停止在付费查询之前。

返回 `stage="awaiting_advice"`、随机 `report_id`、Python 评分、每词真实量与状态、覆盖和来源说明；`advice=null` 明确表示 Agent 尚未提供建议。没有另一个模型服务参与。查询失败仍可返回无数据报告，综合分 null。

## 3. 完整评分卡与文字

根据返回数据撰写建议，再调用 `complete_report`：

```json
{
  "report_id": "用 analyze_title 返回的32位报告ID替换",
  "advice": {
    "analysis": "现有数据仅说明外部搜索需求。编辑判断：明确工具和用途能帮助读者识别主题。",
    "keyword_suggestions": ["保留 Python 与自动化办公主题，避免泛化热词。"],
    "recommended_titles": [
      {"title": "Python 自动化办公：如何减少重复工作？", "direction": "明确工具与用途"},
      {"title": "减少重复工作，如何用 Python 自动化办公？", "direction": "问题前置，保留原标题事实"}
    ]
  }
}
```

示例分析用于说明结构，实际分析必须依照查询结果撰写，不能无论数据怎样都复制。分析不承担数据来源职责。建议文本不重复数值，数值由卡片与工具文字直接显示。不得新增原标题没有的数字、新闻、人物表态、收益保证；推荐标题仅允许原标题词与必要语法词重组。无法证明原标题事实，仍需作者核对正文。

服务按 ID 读取自己的数据副本，Agent 无法提交替换后的分数、搜索量、市场、时间窗或公式版本。建议通过结构与主题校验后返回 `stage="complete"`、`advice.origin="agent"`，包含完整内容、结构化报告和标准 MCP Apps UI 资源引用。评分及查询成本与第二步完全一致。

校验失败保留报告，可只修正建议重试，无新的外部请求；报告最多128份，30分钟过期，重启会丢失。过期/容量淘汰会给明确错误，可重新查询；关键词 SQLite 缓存独立持久化。

不支持 MCP Apps 的客户端也能读取最终工具的完整文字，包含评分/不足状态、关键数据、分析、关键词建议和推荐标题。中间报告会明确显示“等待 Agent 建议”，不能把中间状态称为完整报告。只有 MCP 服务但未加载 Skill 时，Agent 须按工具描述自行执行这三步。
