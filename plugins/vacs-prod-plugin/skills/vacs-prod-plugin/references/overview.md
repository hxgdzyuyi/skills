# VACS MCP API 总览

所有路径都需要 `Authorization: Bearer <mcp_oauth_token>`。该 token 绑定一个用户和一个项目；服务端会注入 `project_id`。

调用 `/api/mcp/current-project/...` 请使用 `request_api`，读取这些文档请使用 `read_api_doc`。所有 API 响应格式都是 `{success,data,error?}`。

## 术语表 / 资源名速查

资源名按业务层级理解：`project` 是当前作品；`chapter` 是故事章节；`comic_chapter` 是把某个章节转成漫画制作结构后的漫画章节；`section` / `comic_section` 是漫画章节里的条漫生成单元；`storyboard` 是每个 section 的文字分镜脚本。

- `project`：作品本身，MCP token 已绑定一个当前 project，所以调用 current-project API 时不要传 `project_id`。
- `workspace`：工作区聚合视图，不是单张表；通常一次返回 project 摘要以及多个子资源列表，适合刷新界面或拿整体上下文。
- `story`：故事阶段内容的统称，包含章节正文、故事设定、故事生成来源和 Story 提示词等。
- `story_profile`：故事设定资料，包括世界观、梗概、一句话故事、人物小传等。
- `story_source`：故事生成或上传的来源记录，用来追踪手工上传、AI 生成、追加下一章等任务状态。
- `chapter`：故事章节，使用 `chapter_code` 标识卷/章，例如 `vol01.ch01`。
- `chapter_story`：某个 chapter 的正文版本；接口里更新章节正文时通常写的是当前 chapter story。
- `comic_chapter`：漫画章节，通常由一个 story chapter 生成，包含多个按 `section_no` 排序的 sections。
- `section` / `comic_section`：漫画 chapter 内的最小条漫生成单元；一个 section 通常对应一段 storyboard，以及一张宽高比约 1:3 的竖向 section image。
- `storyboard`：完整拼写是 `storyboard`，不是 `storybod`；它是某个 section 的 Markdown 漫画脚本，用来描述核心剧情目标、关键视觉瞬间、镜头/动作/对白等图片生成所需信息。
- `section_image`：根据 section storyboard 和 Premise 设定参考生成的竖向条漫图片。
- `premise`：设定阶段内容的统称，包含风格、设定资产、设定来源、标签和 Premise 提示词等。
- `premise_asset`：Premise 设定资产，例如人物、场景、道具、阵营、风格参考图等，可带图片和标签。
- `source`：来源或任务输入记录；`story_source` 偏故事生成，Premise `sources` 偏设定导入/拆解。
- `prompt`：项目级提示词配置；`story_prompts`、`chapter_prompts`、`premise_prompts` 分别影响不同生成流程。
- `variant`：候选版本；`storyboard_variants` 是 section 分镜脚本候选，`image_variants` 是 section 图片候选，选择 variant 通常只移动当前指针，不重新生成。
- `snapshot`：某个漫画 chapter 的整章历史快照，保存 chapter 和 sections 的当时状态，用于恢复。
- `export`：导出记录；`chapter_export` 导出单章漫画，`project_export` 导出整个项目漫画，ready 后可能带短期签名 `download_url`。
- `trash`：软删除回收站；带 `/trash` 的列表接口读取已删除资源，`/restore` 接口恢复资源。

命名规律：复数路径通常是列表或创建资源，例如 `/chapters`；带 `:id` 的路径通常操作单个资源，例如 `/chapters/:chapter_id`；`variants/:variant_id/select` 表示选择候选为当前版本；`.../generations` 通常表示创建异步 AI 生成任务；`.../exports` 通常表示创建或读取导出记录。

## `response_filter`

`response_filter` 用来在 MCP 返回前从完整 JSON 响应中只提取当前任务需要的字段，减少上下文占用，也避免把大段正文、图片签名 URL、完整 workspace 等无关数据带回给 LLM。

列表接口请求时，如无必要，尽量少获取属性；优先只取 `id`、`title`、`status`、`chapter_code`、`section_no`、`created_at` 等用于判断和下一步调用的字段，需要详情时再读取单对象或更精确的字段。

## 当前项目 API

- `GET /api/mcp/current-project`：读取当前项目详情和故事工作区聚合数据。文档：`current-project/project.md`
- `PATCH /api/mcp/current-project`：更新当前项目的标题、语言等可编辑基础字段。文档：`current-project/project.md`
- `GET /api/mcp/current-project/overview`：读取轻量项目总览和资源数量，用于判断下一步要查哪个资源。文档：`current-project/overview.md`
- `GET /api/mcp/current-project/story-workspace`：读取 Story 制作工作区，包含章节、漫画章节、故事设定和提示词等聚合数据。文档：`current-project/story-workspace.md`
- `GET /api/mcp/current-project/story-profile`：读取当前项目的故事设定。文档：`current-project/story-profile.md`
- `PATCH /api/mcp/current-project/story-profile`：更新当前项目的故事设定字段。文档：`current-project/story-profile.md`
- `GET /api/mcp/current-project/story-prompts`：列表读取 Story 生成相关提示词。文档：`current-project/story-prompts.md`
- `PATCH /api/mcp/current-project/story-prompts`：批量更新 Story 生成相关提示词。文档：`current-project/story-prompts.md`
- `GET /api/mcp/current-project/premise-style-prompts`：读取 Premise 风格提示词和整体风格设置。文档：`current-project/premise-style-prompts.md`
- `PATCH /api/mcp/current-project/premise-style-prompts`：更新 Premise 风格提示词或整体风格设置。文档：`current-project/premise-style-prompts.md`
- `GET /api/mcp/current-project/premise-prompts`：读取 Premise 生成相关提示词。文档：`current-project/premise-prompts.md`
- `PATCH /api/mcp/current-project/premise-prompts`：更新 Premise 生成相关提示词。文档：`current-project/premise-prompts.md`
- `GET /api/mcp/current-project/chapter-prompts`：读取章节生成相关提示词。文档：`current-project/chapter-prompts.md`
- `PATCH /api/mcp/current-project/chapter-prompts`：更新章节生成相关提示词。文档：`current-project/chapter-prompts.md`
- `PATCH /api/mcp/current-project/ai-model-settings`：更新当前项目的 AI 模型配置。文档：`current-project/ai-model-settings.md`
- `POST /api/mcp/current-project/story-uploads`：上传带章节编码的故事文件并写入 Story 工作区。文档：`current-project/story-uploads.md`
- `POST /api/mcp/current-project/ai-story-generations`：根据输入提示创建 AI 故事生成任务。文档：`current-project/ai-story-generations.md`
- `POST /api/mcp/current-project/story-next-chapter-generations`：基于现有故事上下文创建下一章生成任务。文档：`current-project/story-next-chapter-generations.md`
- `POST /api/mcp/current-project/story-profile/regenerate`：重新生成当前项目的故事设定。文档：`current-project/story-profile-regenerate.md`
- `GET /api/mcp/current-project/premise`：读取 Premise 工作区，包括项目、风格、设定资产、来源和标签。文档：`current-project/premise.md`
- `GET /api/mcp/current-project/premise-assets`：列表读取 Premise 设定资产，可按标签筛选。文档：`current-project/premise-assets.md`
- `POST /api/mcp/current-project/premise-assets`：新建一个 Premise 设定资产。文档：`current-project/premise-assets.md`
- `GET /api/mcp/current-project/premise-assets/trash`：列表读取已移入回收站的 Premise 设定资产。文档：`current-project/premise-assets-trash.md`
- `POST /api/mcp/current-project/premise-assets/:asset_id/restore`：从回收站恢复一个 Premise 设定资产。文档：`current-project/premise-asset-restore.md`
- `PATCH /api/mcp/current-project/premise-assets/:asset_id`：更新一个 Premise 设定资产。文档：`current-project/premise-asset.md`
- `DELETE /api/mcp/current-project/premise-assets/:asset_id`：删除一个 Premise 设定资产。文档：`current-project/premise-asset.md`
- `GET /api/mcp/current-project/premise-assets/:asset_id/variants`：列表读取某个 Premise 设定资产的图片/内容候选版本。文档：`current-project/premise-asset-variants.md`
- `POST /api/mcp/current-project/premise-assets/:asset_id/variants/:variant_id/select`：选择某个 Premise 设定资产候选版本为当前版本。文档：`current-project/premise-asset-variants.md`
- `POST /api/mcp/current-project/premise-text-imports`：导入文本并创建 Premise 来源处理任务。文档：`current-project/premise-text-imports.md`
- `POST /api/mcp/current-project/premise-asset-breakdowns`：创建 Premise 设定资产拆解任务。文档：`current-project/premise-asset-breakdowns.md`
- `GET /api/mcp/current-project/chapters`：列表读取当前项目的故事章节。文档：`current-project/chapters.md`
- `POST /api/mcp/current-project/chapters`：手动创建一个故事章节。文档：`current-project/chapters.md`
- `GET /api/mcp/current-project/chapters/trash`：列表读取已移入回收站的故事章节。文档：`current-project/chapters-trash.md`
- `PATCH /api/mcp/current-project/chapters/:chapter_id/story`：更新指定章节的正文和标题等故事内容。文档：`current-project/chapter-story.md`
- `POST /api/mcp/current-project/chapters/:chapter_id/restore`：从回收站恢复指定故事章节。文档：`current-project/chapter-restore.md`
- `POST /api/mcp/current-project/chapters/:chapter_id/comic-sections`：在指定章节下手动追加一个漫画 section。文档：`current-project/comic-sections.md`
- `GET /api/mcp/current-project/chapters/:chapter_id/comic-snapshots`：列表读取指定章节的漫画文档历史快照。文档：`current-project/comic-snapshots.md`
- `GET /api/mcp/current-project/chapters/:chapter_id/comic-snapshots/:snapshot_id`：读取一个漫画章节快照详情及其 sections。文档：`current-project/comic-snapshot.md`
- `POST /api/mcp/current-project/chapters/:chapter_id/comic-snapshots/:snapshot_id/restore`：将指定章节的漫画文档恢复到某个历史快照。文档：`current-project/comic-snapshot-restore.md`
- `DELETE /api/mcp/current-project/chapters/:chapter_id`：删除指定故事章节并返回更新后的工作区。文档：`current-project/chapter.md`
- `GET /api/mcp/current-project/comic-chapters`：列表读取漫画章节及其 sections。文档：`current-project/comic-chapters.md`
- `POST /api/mcp/current-project/comic-chapters`：根据章节正文或输入文本创建漫画 storyboard 生成任务。文档：`current-project/comic-chapters.md`
- `DELETE /api/mcp/current-project/comic-sections/:section_id`：删除一个漫画 section 并重排同章节内剩余 sections。文档：`current-project/comic-section.md`
- `PATCH /api/mcp/current-project/comic-sections/:section_id/storyboard`：更新一个漫画 section 的 Markdown storyboard。文档：`current-project/comic-section-storyboard.md`
- `GET /api/mcp/current-project/comic-sections/:section_id/storyboard-variants`：列表读取某个 section 的 storyboard 候选版本。文档：`current-project/comic-section-storyboard-variants.md`
- `POST /api/mcp/current-project/comic-sections/:section_id/storyboard-variants/:variant_id/select`：选择某个 storyboard 候选版本为当前版本。文档：`current-project/comic-section-storyboard-variants.md`
- `GET /api/mcp/current-project/comic-sections/:section_id/image-variants`：列表读取某个 section 的图片候选版本。文档：`current-project/comic-section-image-variants.md`
- `POST /api/mcp/current-project/comic-sections/:section_id/image-variants/:variant_id/select`：选择某个 section 图片候选版本为当前版本。文档：`current-project/comic-section-image-variants.md`
- `POST /api/mcp/current-project/comic-sections/:section_id/image-generations`：根据指定 section storyboard 创建竖向条漫图片生成任务。文档：`current-project/comic-section-image-generations.md`
- `GET /api/mcp/current-project/chapter-exports`：分页列表读取章节导出记录。文档：`current-project/chapter-exports.md`
- `GET /api/mcp/current-project/chapter-exports/:export_id`：读取一个章节导出记录和可用下载信息。文档：`current-project/chapter-export.md`
- `POST /api/mcp/current-project/chapters/:chapter_id/exports`：为指定章节创建漫画导出任务或复用可用导出。文档：`current-project/chapter-export.md`
- `GET /api/mcp/current-project/project-exports`：分页列表读取项目导出记录。文档：`current-project/project-exports.md`
- `GET /api/mcp/current-project/project-exports/:export_id`：读取一个项目导出记录和可用下载信息。文档：`current-project/project-export.md`
- `POST /api/mcp/current-project/project-exports`：创建整个项目的漫画导出任务或复用可用导出。文档：`current-project/project-export.md`
- `GET /api/mcp/current-project/llm-logs`：分页/筛选读取当前项目相关的 LLM 调用日志。文档：`current-project/llm-logs.md`
- `POST /api/mcp/current-project/files/direct-uploads`：为文件直传创建上传结果记录并返回可访问文件信息。文档：`current-project/files-direct-uploads.md`

`response_filter` 示例：

- `.data.project.id`
- `.data.items[] | {id, title}`
- `.data.assets[] | {id, title, image: {url}}`
