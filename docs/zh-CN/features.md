# 功能详解

[English](../features.md) · [繁體中文](../zh-TW/features.md) · **简体中文**

一个本地优先的知识与记忆档案，具备分支式文件库、线性记忆时间线、
混合检索（hybrid retrieval）以及有据可依的 AI 回答。每个账户都有
自己的私有档案；一个 root 账户管理成员资格与共享运行时设置。

Apsor Archive 不是一份笔记列表。它是一个为少量、有针对性的工具调用
而设计的检索界面：搜索一段文字、读取它的邻近内容、沿路径行走、
采样一个时期、写入一条新记忆，或追溯一条被取代的记忆。每个结果都
带有来源、分块编号和时间。

> 状态：v0.1.0 — 文件/记忆档案、root 加每用户账户、持久化的 Pi 形态
> agent（运行时限制由数据库支撑）、压缩、并行工具、SSE 聊天、已保存
> 问题问答库、持久化异步摄取、专用的 PDF/DOCX/PPTX/电子表格/图像/文本预览引擎、
> 一个文件夹工作区，以及一个三栏聊天工作区。


## 亮点

- **文件有谱系。** 路径是一个分支，而不是一次覆盖。重新上传一个
  文件会生长出新的叶子；上一版仍可作为历史被寻址。
- **摄取是持久化的。** 一次上传或直接文本可以立即返回一个
  `file_ingest_job`，同时由有界 worker 解析、分块、嵌入并发布它。
  队列在重启后仍然存在，会报告进度，并且绝不会暴露只索引了一半的文件。
- **文件库是一个文件夹工作区。** 文件夹是一等对象：就地创建它们、
  把文件拖放到文件夹卡片上上传、把文件卡片拖到另一个文件夹以移动它，
  并在需要独立的第二条记录时使用显式的“复制”操作。
- **Agent 只有一个工作区。** 聊天是一张三栏工作台：可折叠的对话抽屉、
  流式对话记录，以及带有可拖动且会持久化的分隔条的工具检查器。
  没有第二个输入框，也没有命令面板。
- **Agent 的限制由数据库支撑。** 步骤与工具上限、并行宽度、结果预算和
  压缩控制都存放在一行经过校验的 `agent_config` 记录中，无需重启即可
  应用于新的运行。每个账户的主模型与上下文预算是独立的分配：上下文窗口
  是真正的每账户输入预算，而不是模型元数据，Agent 会在本地强制执行它，
  而不是让轮次失败。
- **聊天模型按账户分配。** root 会把每个账户关联到一个已保存的聊天端点，
  以及供 Agent 聊天使用的自由文本模型和推理力度，并为摘要、记忆、摄取和
  视觉关联第二个端点。变更后的连接必须通过真实的提供商探测才能保存。
  提供商行持有加密密钥，因此轮换密钥会影响分配到该端点的每个账户。
- **长线程可以被折叠或清空。** 压缩会写入一个摘要边界；清空会启动
  一个空的活动上下文。两种情况下，完整的对话记录仍然可读。
- **记忆是线性的、可追溯的。** 新的判断可以取代旧的判断。
  旧记忆会离开检索界面，但仍可通过其链条读取。
- **搜索是混合式的。** 基于 CJK 二元组和拉丁词元的 BM25 与向量
  召回并行运行。结果会去重并融合，同时记录原因。过去的对话消息也会以原始的
  256 字符窗口建立索引；另一条 cosine → BM25 → RRF 通道会返回最佳的 15 个
  窗口，Agent 可以用稳定的消息 ID 展开任何命中结果。
- **时间采样是诚实的。** 时间线为每种事件类型最多返回五个锚点，
  并准确报告跳过了多少事件。人类时间线页面则用 `complete=true`
  获取所选窗口的全部事件，并在向下滚动时自动加载更早的窗口。
- **AI 回答有据可依。** 分配的聊天模型收到的是检索到的段落，而不是整个
  文件库；每条论断都必须带引用。没有可用的分配时，Agent 轮次会以稳定
  代码失败关闭。
- **问题比对话更长久。** 可以在还没有答案时保存问题，稍后再提问，
  并把答案、引用、运行状态以及指向对话的链接保留在同一行。编辑问题
  会清除过期的答案，而不是在屏幕上留下一对不匹配的内容。
- **聊天图像是临时的。** 粘贴到聊天输入框的截图会立即上传（逐张显示字节
  进度）到当前登录账户的 `users/{user_id}/chat-temp/` 对象存储区，经缩小和
  重新编码后，列在可移除的临时图像管理器中。在所有选中的图像都保存完成前，
  无法发送。移除尚未发送的图像或离开聊天，会中止其上传并立即丢弃暂存行；
  关闭标签页后遗留的暂存图像，会在数据库配置的存活时间（默认一小时）后过期。
  发送消息时，会先把对象提升到 `users/{user_id}/chat-images/` 再认领该行，
  因此已发送的图像会一直保留，直到所有者删除。提供商收到的是 OpenAI 兼容的
  `image_url` 部分。删除聊天图像会移除对象，并在对话记录中留下如实的占位
  说明。聊天图像不是档案文件，也无法被搜索。
- **图像保存在文件库中。** 图像是一条普通的文件记录，带有原始字节、
  路径和分块。支持视觉的聊天提供商会补充 OCR、GitHub-Flavored Markdown
  表格和完整的视觉描述；OCR 文本保留原文语言，描述语言与图像／文档提示词
  模板则是仅限 root 的设置。每个视觉提取的文件都会记录实际发送提示词的
  SHA-256、模式和描述语言。没有这样的提供商时，由文件名派生的说明文字可
  让本地上传仍可搜索。不存在单独的图像索引。
- **视觉提示词可完整编辑，但不做版本历史。** root 可以替换完整的图像与
  扫描页系统提示词。保存时只验证九个输出 JSON 键仍然存在；当前模板存放
  在 `ingest_config`。现有文件会保留当前提取结果，直到显式重新摄取并创建
  新的文件版本。
- **文档自行选择提取器。** PDF 先尝试文本，扫描页则回退到视觉提取。DOCX、
  PPTX、TXT、JSON、CSV 和日志使用文本，并辅以 AI 结构化元数据；图像使用
  视觉或文件名回退。XLSX、XLS、XLSM 和
  ODS 工作簿会逐工作表读成 Markdown 表格，包含日期、数字、合并标题、隐藏
  工作表和公式回退；它们永远不会进入视觉流程。
- **界面支持三种语言。** 可以在设置页面切换英语、繁体中文和简体中文。
  选择按浏览器存储，应用于整个界面，但从不应用于档案内容。
- **档案是私密的、多账户的、本地优先的。** 一个 root 账户管理账户和
  全局运行时设置；其他每个账户都获得一个私有档案，包含文件、文件夹、
  分块、记忆、摘要、对话、条目、运行、审批、已保存的问题、提示词和
  个人资料卡。PostgreSQL 行级安全在每张私有表上强制归属，因此即使
  缺少查询过滤条件，也无法暴露他人的档案。密码使用 Argon2，会话使用
  HttpOnly cookie。请在自己的机器上运行；只有在具备自己的访问控制时，
  才把它放到 Cloudflare Tunnel 之后。
- **原始字节存放在 S3 兼容存储中。** 默认是随附的 RustFS 服务；也可以在
  设置向导中改选 Cloudflare R2、任何 S3 端点或本地磁盘。读取时遵循每一行
  记录的存储后端，因此分阶段迁移可以提供混合档案。存储桶始终保持私有，
  应用从不签发预签名 URL 或公开 URL。

## 工具接口

档案提供六个小型 HTTP 工具。每个 JSON 端点对应一个 Agent 可以调用的
检索或记忆操作；每个负载都被刻意做得足够小，以便 LLM 按顺序使用。

| 工具 | 端点 | 返回内容 |
|---|---|---|
| `search_knowledge` | `GET /api/v1/search?query=&result_number=2` | 来自 BM25 + 向量的每种档案来源类型的顶部结果，使用 RRF 融合；另加最佳的 15 个过去对话窗口 |
| `read_file` | `GET /api/v1/files/{file_id}/chunks/{chunk}?chunk_range=1` | 一个从 1 开始的分块窗口 |
| `read_timeline` | `GET /api/v1/timeline?year=&month=&day=&day_range=1` | 默认稀疏：每种类型最多五个采样事件、密度以及跳过计数；`complete=true` 返回整个窗口 |
| `read_path` | `GET /api/v1/paths?path=/history&path_depth=1&fuzzy_search=` | 目录和文件，或模糊路径匹配 |
| `save_memory` | `POST /api/v1/memories` | 一条带有自动生成标题的新记忆、它取代的已弃用记忆，以及任何新摘要；省略 `content` 可在没有替代内容的情况下弃用 `supersedes` id |
| `read_memory` | `GET /api/v1/memories/{memory_id}?memory_range=1&trace_history=true` | 目标、邻居、取代关系、后继者和链条 |

Agent 工具与 `/api/v1/tools/read_timeline` 始终使用稀疏默认值；时间线页面会
为所选窗口加上 `complete=true`，并在向下滚动时自动加载上一个窗口。完整响应
报告 `mode="complete"`、`sampled == total == len(events)`、`skipped=0`、空的
`skips`，并且每个事件的 `anchor=null`。页面会把事件主轴排除在页面上下文之外，
因此完整列表不会成为 Agent 的上下文。

持久化档案 agent 暴露十个模型工具：上述六个加上
`present_resource`、`web_search`、`web_fetch` 和 `history_message`。HTTP 示例使用
显式参数；HTTP 服务器默认值是 `result_number=2`、`chunk_range=1`、
`day_range=1`、`path_depth=1` 和 `memory_range=0`。文本按约 4,000
字符分块，重叠 500 字符；现有文件在重新摄取之前保留其原始分块
边界。过去的对话消息使用另一种固定窗口：256 字符、32 字符重叠（步幅
224）。Agent 的工具架构会选择自己的默认值，例如 `result_number=8`
和 `day_range=7`。`history_message` 接受 `<history_message>` 搜索命中上
显示的 `id`，并返回完整消息以及有界的相邻消息。对于外部 LLM 调用者，单独的 `/api/v1/tools/*`
外观会把相同的服务渲染为紧凑 XML；持久化 agent 通过自己的注册表
直接调用这些服务。

`present_resource` 返回诸如 `/viewer/file/{id}?chunk={n}` 或
`/viewer/memory/{id}` 的资源 URL，并且从不抓取资源。客户端会把
文件链接重定向到文件库预览模态框，把记忆链接重定向到记忆阅读器。

在聊天检查器中，`web_search` 会展开查询、提供商、检索时间以及每个
结果的可点击 URL、摘录和分数；`web_fetch` 会展开源元数据和抓取到的
正文。网页结果 URL 和抓取内容都有复制操作。记忆引用会向人显示为
`Memory: <generated title>`，而模型和工具提示保留稳定的
`[memory:id]`。记忆文本、每个文件分块以及对话记录也都有单击复制
操作。

每条记忆行都存储一个简短的自动生成 `title`。在保存和编辑时，后端
会在单次插入或更新之前向配置的聊天提供商请求一个名称，因此正文和
标题会原子地存储。如果提供商不可用，正文的前 80 个字符会成为回退
标题。聊天会把每个记忆引用渲染为数字标签加上该名称；较早的对话
记录会通过 `read_memory` 按需解析缺失的名称。

`save_memory` 有一种不提供替代内容的弃用形式：省略 `content`，
在 `supersedes` 中传入现有 id，并可选地包含 `reason`。后端会把这些
行标记为已弃用，盖上 `deprecated_at`，把它们的搜索分块标记为
非当前，并且不写入新记忆。带有 `content` 的同一调用会保留原来的
取代行为。

持久化的 `pi.tool-result` 条目还携带仅用于 UI 的 `data`：有界摘录、
维度、标签以及用于展开检查器的查看器 URL。这个负载永远不会进入
提供商消息；模型仍然只看到 XML 工具结果。

`save_memory` 是一个写入操作。`save_memory_requires_approval` 运行时
设置（默认 `true`，可在 **设置 → Agent 运行时 → 工具执行** 中编辑）
控制它如何被授权：

- **开启（默认）：** 循环不会执行写入。它会持久化一行
  `agent_approval`，此时不追加工具结果，把运行移到 `waiting`，并
  发出带有有界预览的 `approval_required`。仅弃用的调用会预览目标 id
  和原因，而不是提议的正文。`POST
  /api/v1/agent/approvals/{approval_id}/approve` 是执行写入的唯一
  路径；`.../reject` 会追加一个 `memory_rejected` 工具结果并在不写入
  的情况下继续。模型的 `user_confirmed` 参数在授权中被忽略。
- **关闭：** 不会创建等待中的运行或审批行。后端自己授权经过校验的
  写入（工具注册表中 `approved=True`），调用在同一轮内完成。模型
  提供的 `user_confirmed` 仍然永远不会授权写入。

重复或过期的审批处理会返回 `409 agent_approval_not_pending`，已归档或
已删除的对话会失败关闭。禁用该设置不会批准或取消已经存在的审批；
它们仍然是显式的待处理行，其卡片会继续渲染。写入之后，展开的
检查器仍会渲染产生的回执。

其他接口：`POST /api/v1/files`（多模态摄取）、`POST
/api/v1/files/text`、`DELETE /api/v1/files/{file_id}`、
`GET /api/v1/paths`、`GET /api/v1/memories`、
`POST /api/v1/memories`、`PATCH /api/v1/memories/{memory_id}`
（编辑文本；标题会重新生成）、
`POST /api/v1/memories/{memory_id}/deprecate`（直接停用，可选
`reason`）、`GET /api/v1/memories/{memory_id}/related` 和
`GET /api/v1/memories/related/files/{file_id}`（根据已存储的嵌入和关键词找出
关联记忆；不调用提供商）、`POST /api/v1/summaries`、`GET /api/v1/stats`、
`GET /api/v1/health` 和 `GET /api/v1/ai/status`。`ai/status` 报告部署全局的
运行时，供 root 诊断使用；它不是某个账户的模型分配。

### 文件夹工作区

`/library` 是一个文件夹优先的工作区。面包屑和文件夹栏描述你所在的
位置；主区域显示当前路径的文件夹卡片和文件卡片。之前的表格仍作为
紧凑列表视图提供，用于密集浏览，需要用 `view=list` 显式选择。

- **新建文件夹** 会创建请求的文件夹以及任何缺失的祖先。该操作是
  幂等的：重复执行会返回同一个文件夹，状态码 `201`。
- **拖放上传** 接受从桌面拖放到文件夹卡片或当前文件夹表面的文件。
  上传使用与上传对话框相同的摄取路径、扩展名允许列表和服务器限制：
  每个上传文件 10 MB，以及 `.md`、`.markdown`、`.txt`、`.csv`、
  `.json`、`.jsonl`、`.toml`、`.ini`、`.env`、`.log`、`.pdf`、`.docx`、
  `.pptx`、`.xlsx`、`.xls`、`.xlsm`、`.ods`、`.jpg`、`.jpeg`、`.png` 或
  `.webp`。对话框还支持 2 MB 的纯文本创建。拖放的文件永远不会被打开或执行。
- **剪贴板粘贴** 通过同一条摄取路径上传文件。当剪贴板中的名称已存在于目标
  文件夹时，粘贴的文件会获得第一个可用的 ` (n)` 后缀（`image (1).png`），
  而不是悄悄成为新版本；一次粘贴多个同名文件时会依次编号。拖放或使用上传
  对话框则保持显式的同名版本行为。
- **移动与复制** 是显式的。普通拖放到文件夹会移动文件；拖放时按住
  Alt/Option 则会复制它。触摸和键盘用户会得到单独的 **移动** 和
  **复制** 操作，而不是拖拽。
- 一次 **移动** 会保留相同的文件 id、版本、分块、嵌入和原始字节。
  只有 `raw_file_path` 和文件名会改变，因此现有的搜索、时间线、
  引用和查看器链接仍然有效。
- 一次 **复制** 会创建一个新的当前文件 id，版本为 1，在存在已存储
  原始文件时克隆它，重建分块和嵌入，并复制 AI 摘要、标签、文档类型
  和提取方法。两个文件都保持当前且可搜索。
- 移动和复制必须保留原始扩展名。目标被另一个文件夹或当前文件占用
  时返回 `409 tree_path_conflict`；无效路径或更改扩展名返回
  `422 invalid_path`。

| 方法 | 路径 | 请求体 | 用途 |
|---|---|---|---|
| `POST` | `/api/v1/folders` | `{path}` | 创建一个文件夹及缺失的祖先；幂等 `201` |
| `POST` | `/api/v1/files/{file_id}/move` | `{path}` | 就地移动一个当前文件；`200` |
| `POST` | `/api/v1/files/{file_id}/copy` | `{path}` | 把一个当前文件复制为新记录；`201` |

三个端点都要求已认证的账户，并且只操作该账户的文件夹树。当它们
更改文件夹或文件索引时，会递增该账户的档案缓存版本；另一个账户中的
路径是一棵独立的、不冲突的树。

### Agent 对话

`/api/v1/agent` 是一个持久化的、Pi 形态的多轮档案 agent。“Pi 形态”指的是
Pi coding-agent harness 的持久化对话记录模型：对话是一份由不可变条目组成的
追加式日志，提供商上下文会在最新的 reset 或压缩边界之后由该日志重建，而不是
来自可变的聊天数组。Apsor Archive 用 Python 与 PostgreSQL 实现此模型，不
运行 Pi 运行时，也不依赖其软件包。相关数据表如下：

- `agent_conversation` — 对话记录范围、提供商/模型标识和元数据。
- `agent_entry` — 不可变的 `pi.user`、`pi.assistant`、`pi.tool-result`、
  `pi.page-context`、`pi.system`、`pi.reset`、`pi.compaction` 和
  `ui.notice` 条目。`model` 是规范的提供商消息文本；关联的临时图像会在调用
  提供商时具体化为 `image_url` 部分，`data` 仅用于 UI/诊断。
- `agent_run` — 一次提交的持久化状态（`request_id`、状态、中止、
  最后条目、安全错误）。`agent_commit_seq` 对在一个事务中写入的条目
  进行分组。
- `agent_approval` — 针对需要确认的工具调用的一个持久化待处理/
  已批准/已拒绝/已过期人工决定，包括经过校验的参数、安全预览，以及
  用于恢复等待运行的循环快照。
- `agent_chat_attachment` — 属于单个账户的聊天图像，包含对象存储键、经过清理
  的元数据，以及指向发送它们的用户条目的可选链接。尚未发送的图像位于
  `users/{user_id}/chat-temp/`；发送时会提升到 `users/{user_id}/chat-images/`。
  行采用软删除。
- `agent_config` — 单例运行时配置（`id=1`），保存经过校验的令牌、步骤、
  工具、页面上下文、压缩和聊天图像存活时间限制。

用户和 assistant 条目也会以 `source_kind='history'` 复制到共享的扁平分块索引
中，每个 256 字符窗口一行。后台的历史索引器会回填现有对话、跳过只有工具调用
而没有内容的 assistant 条目，并把软删除对话的窗口标记为非当前。Agent 会把
每个命中看作 `<history_message id="...">`，并调用 `history_message` 读取完整的
不可变条目及其相邻条目。

第一个条目是冻结的 `pi.system` 提示词和工具快照。上下文构建器会
确定性地重放条目：它遵循 `head_entry_id` 和 `edits`，保留系统条目，
把工具结果直接移到其 assistant 调用之后，合成缺失的结果，丢弃孤立
结果，并排除失败的 assistant 尝试。工具调用会经过校验并作为结构化
结果返回；工具失败永远不会变成 HTTP 500。

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/v1/agent/conversations` | 创建一个对话及其系统条目 |
| `GET` | `/api/v1/agent/conversations` | 列出活动/已归档的对话，最新活动优先 |
| `GET` | `/api/v1/agent/conversations/{conversation_id}` | 元数据加上第一页条目 |
| `GET` | `/api/v1/agent/conversations/{conversation_id}/entries?after_id=&limit=` | 升序的条目分页 |
| `PATCH` | `/api/v1/agent/conversations/{conversation_id}` | 重命名、归档或恢复 |
| `DELETE` | `/api/v1/agent/conversations/{conversation_id}` | 软删除；条目保留以供审计 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/compact` | 追加一个手动压缩边界 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/clear` | 追加一个重置边界；对话记录会保留 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/fork` | 把截至（含）截止点的条目复制到新线程 |
| `POST` | `/api/v1/agent/attachments` | 上传一张临时聊天图像（`multipart/form-data`，可选 `client_token`） |
| `POST` | `/api/v1/agent/attachments/cancel` | 按 `client_token` 幂等地丢弃暂存上传（`204`） |
| `GET` | `/api/v1/agent/attachments?status=&limit=&offset=` | 列出账户的临时聊天图像 |
| `GET` | `/api/v1/agent/attachments/{attachment_id}/content` | 流式传输一张仍有效的临时图像 |
| `DELETE` | `/api/v1/agent/attachments/{attachment_id}` | 删除对象并软删除其行（`204`） |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/messages` | 追加一个用户条目并运行循环 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/retry` | 重试最近一次失败/取消的运行 |
| `GET` | `/api/v1/agent/conversations/{conversation_id}/approvals?status=` | 持久化的审批，最早的优先（默认 `pending`） |
| `POST` | `/api/v1/agent/approvals/{approval_id}/approve` | 执行一次，追加工具结果，继续 |
| `POST` | `/api/v1/agent/approvals/{approval_id}/reject` | 追加 `memory_rejected`，不写入即继续 |
| `GET` | `/api/v1/agent/tools` | 当前工具目录加上提示词/工具版本 |
| `GET` | `/api/v1/agent/settings/system-prompt` | 列出每个系统提示词分区 |
| `POST` | `/api/v1/agent/settings/system-prompt` | 创建一个分区（`201`） |
| `PUT` | `/api/v1/agent/settings/system-prompt/order` | 重新排序每个分区 |
| `PUT` | `/api/v1/agent/settings/system-prompt/{section_id}` | 替换一个分区 |
| `DELETE` | `/api/v1/agent/settings/system-prompt/{section_id}` | 删除一个分区（`204`） |
| `POST` | `/api/v1/agent/settings/system-prompt/reset` | 用四个初始默认分区替换每个分区 |

`POST /api/v1/agent/conversations/{conversation_id}/messages` 接受
`{content, attachment_ids?, request_id?, page_context?, client_timezone?,
client_utc_offset_minutes?}`，`.../retry` 接受 `{request_id?}`。最多可以附上
四张已暂存的聊天图像；有图像时文本可以为空。两者默认都流式返回
`text/event-stream`。客户端时区会与服务器渲染的 `<current_time>` 块一起存储在
每个用户条目上；该块会恰好在消息文本之后追加一次。排序后的系统提示词分区会在
创建对话时写入，并冻结到该线程中。四个默认值以普通行的形式初始写入；设置页面
让 root 账户可以为整个部署编辑、删除或重新排序每一行。事件名称为
`run_start`、`message_start`、`message_delta`、`reasoning_delta`、
`message_end`、`tool_start`、`tool_end`、`approval_required`、`run_end` 和
`error`。`reasoning_delta` 携带在对应回答或工具调用之前到达的提供商推理文本，
并且永远不会并入 `message_delta`。`run_start` 会报告 `page_context_entry_id`
（或 `null`）、`page_context_attached` 和 `resumed`，让客户端能标记是否写入了
新快照，以及流是否延续一个持久化的等待运行。`tool_start` 和 `tool_end` 还带有
assistant 调用批次的 `parallel`、`batch_size` 和 `parallel_index`。`tool_end`
带有已持久化的工具结果 `data` 负载，以及 `duration_ms` 和 `error_code`，因此
检查器可以在对话记录重新获取完成之前先渲染预览。`message_start` 的
`entry_id=null`，因为 assistant 条目只在 `message_end` 时持久化；增量仅用于
传输。提供商推理会作为有界的显示用遥测保存在 assistant 条目中，并以纯文本
`Thinking` 块显示；它永远不会进入提供商消息、冻结的系统前缀或缓存前缀哈希。
确定性的压缩摘要可能带有一行有界的 `Thinking:`。如果想获取完成的轮次，请改为
发送 `Accept: application/json`。SSE 响应会设置
`Cache-Control: no-cache, no-transform` 和 `X-Accel-Buffering: no`，并且
Starlette 的 GZip 中间件会排除 `text/event-stream`。

每个对话一次只允许一个活动运行。默认值允许 6 个并行工具、自动压缩前 75,000
个令牌的活动上下文，以及每个工具 100,000 个结果字符。没有步骤上限、工具调用
上限，也没有累计的每轮令牌上限；轮次只会在最终答案、用户取消或提供商失败时
结束。有效的上下文窗口是部署默认值（1,000,000），除非账户分配了自己的预算；
它是由本地溢出阶梯强制执行的真实出站输入预算，压缩阈值必须低于它。预算估算中，
CJK 字符大约按每个令牌 1.6 个字符计算，ASCII 文本则保持模型目录的比例，并且
当前上下文段中提供商报告的最大成功 `prompt_tokens` 会作为下限。因此，仅提供商
可见的状态块中的 `context_used` 是保守估计，而不是与提供商完全一致的令牌数。
每个结果都会按该单条结果上限独立截断，并附上可见的 `[truncated]` 标记；不存在
整轮的结果预算，也没有第二次摘要调用。100,000 字符的上限大约涵盖二十五个
4,000 字符的分块。这些是运行时设置，不是代码常量；请见上方的
**Agent 运行时设置**。符合条件的工具调用会同时开始，并在启用并行工具时通过
`asyncio.gather` 执行。结果持久化和 `tool_end` 的顺序遵循 assistant 调用顺序，
而不是完成顺序。停用并行工具时，执行按顺序进行，事件会报告 `parallel=false`。

失败或取消的运行可以重试，而不会重复用户条目。当最新条目是失败/取消的
assistant 回答、结尾的硬性上限工具结果（`step_limit`、`token_limit`、
`tool_call_limit` 或 `tool_result_budget_exhausted`），或最后一次流在记录
assistant 条目之前就失败时，聊天工作台和停靠的 agent 都会显示“重试”操作。
重试会为同一个用户条目启动新的运行；UI 不会追加第二条消息，并在流进行中禁用
该操作。如果连溢出阶梯都无法让请求放得下，重试仍可能被提供商拒绝。当最近一次
运行已完成或并非失败/取消时，端点会返回 `409 agent_run_not_retryable`；UI 会在
该错误后重新获取对话记录，让过期的“重试”操作消失。

#### 对 `save_memory` 的人工审批

当 `save_memory_requires_approval=true`（默认值）时，有效的确认调用
永远不会从模型循环中写入。它会持久化 `agent_approval`，包含对话、
运行、工具调用 id、经过校验的参数、安全预览和恢复快照；同一批次中
的安全调用仍会运行并追加其结果。运行变为 `waiting`，SSE 流以
`approval_required` 加上 `run_end {status: "waiting"}` 结束，
assistant 工具调用仍保留在对话记录中。包含多个确认调用的批次会为
每次调用创建一个审批；审批处理必须遵循审批 id 顺序，并且在最后一行
待处理记录处理完毕后，循环继续。

关闭该设置时，经过校验的调用会立即执行，并由后端授权
（`approved=True`），不会创建 `agent_approval` 行，运行正常完成。
模型的 `user_confirmed` 参数在两种模式下都不会授权写入。关闭该
设置不会处理已经存在的审批；它们的卡片仍然存在，需要显式决定。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/agent/conversations/{id}/approvals?status=pending` | 待处理审批，最旧在前 |
| `POST` | `/api/v1/agent/approvals/{approval_id}/approve` | 执行一次，追加结果，恢复 |
| `POST` | `/api/v1/agent/approvals/{approval_id}/reject` | 追加 `memory_rejected`，不写入并恢复 |

两个审批处理端点都接受 `Accept: application/json`，或以 SSE 流式
传输恢复的轮次。它们以 `run_start {resumed: true}` 开始，然后是为
已处理结果发送的 `tool_end`；如果还有另一个审批，它们以
`approval_required` 和 `run_end {status: "waiting"}` 结束，否则正常
循环继续。在该行已处理、已过期或已孤立之后批准会返回
`409 agent_approval_not_pending`；已归档的对话返回
`409 agent_conversation_archived`。

API 重启时，陈旧的 `running` 运行会以 `interrupted` 失败。带有有效
待处理审批的 `waiting` 运行会存活，并仍可从审批端点看到。没有有效
待处理审批的等待运行会以 `approval_orphaned` 失败关闭。暂停是
只追加的：只有 `agent_run`/`agent_approval` 的操作列会改变，真实
工具结果会在决定到达时追加。

对话详情返回第一页条目，UI 通过 **加载更多条目** 加载后续页面。
它还返回 `last_page_context_key`，该值从条目日志读取，而不是从
浏览器存储读取，因此重新加载的对话仍然知道最后附加的是哪个页面
快照。

#### 压缩与清空

当 `auto_compaction_enabled` 为 true，并且估计的活动上下文超过
`compaction_threshold_tokens` 时，系统会在下一次调用提供商前追加
一个 `pi.compaction` 条目。该检查既会在新用户轮次之前运行，也会在
运行中的轮次因工具或页面上下文增长后再次运行，因此上下文塞满时会
压缩，而不是让提供商调用失败：

- 该条目把 `head_entry_id` 设为自身的 id，因此较早的条目保持
  不可变，但落在新的活动上下文之外。
- 它的提供商消息以 `<compaction>` 开头，并携带 `<last_user_input>`
  （压缩前的最后一次用户输入）和 `<summary>`。
- 同一事务按压缩 → 页面上下文（当页面被重新附加时）→ 用户的顺序
  写入，因此模型会在新请求之前看到摘要。

这会启动新的 KV 缓存谱系。系统提示词和工具快照保持冻结，旧对话
记录在 `/chat` 和停靠区仍然可读。

压缩始终是确定性的：永不调用提供商。摘要受
`compaction_max_output_tokens`（默认 2,600）限制，并由 root 可编辑的
`compaction_prompt` 渲染；模板必须包含 `{max_output_tokens}`，旧的字符
上限仍然适用。溢出阶梯也可以为单个对外请求构建临时压缩，而不追加边界。

`POST .../compact` 会从当前活动上下文手动追加相同的边界。
`POST .../clear` 会追加带有自身 `head_entry_id` 且没有提供商消息的
`pi.reset`；对话记录保留，但下一轮从空的活动上下文开始。它们的
操作 id 是 `compactAgentConversation` 和 `clearAgentConversation`。
当有运行处于活动状态时，两个端点都返回
`409 agent_conversation_busy`，并以
`409 agent_conversation_archived` 拒绝已归档的对话。对话记录卡片
会标注边界，并说明较早的行仍然保留但从活动上下文中隐藏。

#### 分叉

`POST .../fork` 接受可选的 `{at_entry_id?, title?}` 请求体，并返回
`201` 和新对话。`at_entry_id` 是一个包含式截止点，必须属于源线程；
默认为最新条目。默认标题是 `Fork of {source.title}`，截断到
200 字符。分叉始终处于活动状态，获得新的 `provider_session_id`，
记录 `parent_conversation_id` 和 `fork_at_entry_id`，并复制截止点
之前的不可变条目，赋予新的 id 和 `commit_seq` 值。头部标记和上下文
编辑会重新映射到复制的条目；截止点之外的引用会被丢弃。源对话及其
条目永远不会被修改。

分叉只复制对话记录条目。运行、重试状态和审批状态不会被复制，因此
下一条用户消息会针对复制的上下文启动新的运行。已归档的源返回
`409 agent_conversation_archived`；活动运行返回
`409 agent_conversation_busy`；来自另一个对话的截止点返回
`400 agent_fork_entry_invalid`；缺失或软删除的源返回
`404 agent_conversation_not_found`。在 UI 中，线程栏为活动线程提供
**分叉** 操作（对已归档线程禁用并给出说明），用户/assistant 条目
提供 **从此处分叉**。成功会显示 toast、使线程列表失效，并导航到
新线程；页眉显示 `Forked from #<id>`，并带有指向源的链接。

#### 页面上下文与 KV 缓存

客户端可以随消息发送一个 `page_context` 对象：

| 字段 | 类型 | 规则 |
|---|---|---|
| `key` | string | 稳定的页面标识；1–512 字符 |
| `path` | string | 人类可读的路由加上有意义的查询参数；1–1024 字符 |
| `title` | string 或 null | 可选的页面标题；最多 300 字符 |
| `text` | string | 页面上可见的纯文本；服务器裁剪前为 1–12,000 字符 |

服务器会规范化行尾和空白，折叠重复的空行，并把存储的快照上限设为
6,000 字符。条目在 `data` 中存储 `page_key`、`path`、可选的
`title`、`text_chars` 和 `truncated`，并在 `<page_context>` XML
信封内给模型发送一条用户角色消息。系统提示词把该信封标记为数据，
永远不是指令。

页面上下文是只追加的，并且会保留缓存：

- `begin_message` 会把传入的 key 与最新上下文边界（压缩或重置）处
  或之后最新的 `pi.page-context` 条目比较。去重和
  `last_page_context_key` 都限定在该活动段内。
- 只有不同的 key 才会追加新快照。从同一页面再次提问不会重复它。
- 压缩或清空边界会隐藏较早的快照，因此同一页面可以在边界之后
  重新附加。
- 快照条目和用户条目共享一个 `commit_seq`；快照紧挨在用户条目之前
  排序，当两者都为同一轮写入时，位于自动压缩条目之后。
- 较早的条目永远不会被重写，因此稳定的系统/工具前缀和先前的对话
  前缀仍然是有效的 KV 缓存谱系。压缩或重置边界会刻意启动新的谱系。

当前的 SPA 不会附加页面快照，因为浮动停靠区和跨页面输入框已被
移除。API 字段仍对外部客户端可用；当存在快照时，对话记录会把它
渲染为紧凑的上下文卡片，而不是用户问题。

测试通过设置 `app.state.agent_chat_generator` 或覆盖
`get_agent_chat_generator`，从
`app/module/agent/test/fake_chat_generator.py` 注入确定性的
`FakeChatGenerator`；不会进行 DeepSeek 调用。

#### 已知限制

- 重试会以相同的运行时快照策略启动新的运行，但不会增加任何预算。
  已经耗尽令牌或工具结果预算的对话记录可能再次触及相同限制。
- 审批处理是单写入者的。如果进程在审批被认领之后、其工具结果被
  追加之前崩溃，等待运行会在下次启动时失败关闭，而不是自动重试写入。
- 关闭 `save_memory_requires_approval` 只影响新的调用。在它开启时
  创建的待处理审批会保持待处理，直到被显式批准或拒绝；它们永远不会
  因设置更改而被自动批准。

### 已保存的问题

`/api/v1/agent/questions` 是对话 agent 旁边的一个小型问答库。
已保存的问题可以在任何答案存在之前就存在。提问它会创建一个新对话，
运行一次 JSON agent 轮次，并把结果写回同一行，因此问题保持稳定的
id 及其最新答案。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/agent/questions?limit=&offset=` | 列出已保存的问题，最新在前；`limit` 为 1–100（默认 50） |
| `POST` | `/api/v1/agent/questions` | 保存一个问题；`201`；只接受 `question` |
| `PATCH` | `/api/v1/agent/questions/{question_id}` | 编辑问题文本 |
| `DELETE` | `/api/v1/agent/questions/{question_id}` | 删除问题及其存储的答案；`204` |
| `POST` | `/api/v1/agent/questions/{question_id}/ask` | 运行一个轮次并持久化其结果 |

列表响应体是 `{resources, total, limit, offset}`。全部五个操作都要求
已认证的账户，并且只暴露该账户已保存的问题。创建和更新会拒绝未知
字段，因此客户端无法提供答案。`question` 会被去除首尾空白，并限制
为 32,000 字符。

该表（`saved_question`）存储：

- `id`、`question`、可空的 `answer`，以及作为 JSONB 数组的
  `citations`；
- 可空的 `conversation_id`，带有 `ON DELETE SET NULL`，因此删除
  对话会保留已保存的答案；
- 最近一次提问的 `run_status`、`error_code` 和 `error_detail`；
- `created_at`、`updated_at` 和 `last_asked_at`。

`PATCH` 会把规范化后的文本与存储的文本比较。问题发生变化会清除
`answer`、`citations`、`conversation_id`、所有运行元数据和
`last_asked_at`；未更改的编辑只刷新 `updated_at`。这可以防止旧答案
被展示在新措辞之下。

`POST .../ask` 会创建一个以问题为标题的新对话（最多 80 字符），
追加用户条目，使用现有运行时快照策略运行恰好一个 agent 轮次，并
记录最终答案、引用标记、对话 id 和 `run_status`。提供商或工具失败
仍然是 `200`，带有 `run_status="failed"` 及其
`error_code`/`error_detail`，因此问题会保留。缺少 AI 配置会保留
现有的 `503 agent_not_configured` 响应。再次询问同一问题会创建
另一个对话，并替换同一已保存行上的答案。

`/questions` 页面是一个次级工作区，从搜索页面和方法说明页脚链接
进入。它使用生成的 hooks，并提供创建、列出、分页、编辑、删除和
提问操作。每张卡片显示其状态、答案、引用标签、运行错误、最近提问
时间，并在存在对话时显示 **打开对话** 链接。提问是同步 JSON 请求，
因此卡片会在轮次所需的数秒内显示待处理状态。

### 聊天阅读室

`/chat` 和 `/chat/:conversationId` 是 agent 的持久化阅读室。线程栏
列出活动和已归档的对话，并支持重命名、归档/还原、删除和新建线程；
页面把不可变条目渲染为保管者边注、档案页、田野笔记式工具结果和
结构化资源卡片。输入框通过 SSE 流式传输，支持 Cmd/Ctrl+Enter 和
停止操作，并在运行结束时刷新线程列表和活动对话记录（不会重新获取
其他对话）。

线程卡片会为最近一次失败/取消的 assistant、末尾的硬限制工具结果
（`step_limit`、`token_limit`、`tool_call_limit` 或
`tool_result_budget_exhausted`），或在 assistant 条目之前的流失败
显示 **重试**。重试会调用现有的重试端点，复用同一个用户条目，不追加
重复消息，并在流处于活动状态时禁用。`409 agent_run_not_retryable`
响应会触发对话记录重新获取，使过期操作消失；重试可能再次触及相同
预算。

当运行因 `save_memory` 暂停时，一条持久化的审批卡片会出现在线程和
停靠区中。它显示提议的记忆、取代/发生时间上下文、写入风险，以及
**批准写入** / **拒绝** 操作。该卡片从持久化审批端点加载，因此
重新加载后仍然存在；当审批处理正在流式传输或线程已归档时，它会被禁用。
批准会恢复运行并追加真实的工具结果；拒绝会追加 `memory_rejected`，
并且永远不会写入。

同一工作台为活动上下文提供 **压缩** 和 **清空**。压缩是立即的；
清空会要求一次内联确认。两者在流运行时和已归档线程上都会被禁用。
`409 agent_conversation_busy` 响应会显示稳定的错误消息并重新获取
线程。随后的压缩/重置边界会渲染为上下文卡片，而不是用户消息；
卡片会说明较早的对话记录行仍然保留，但从模型的活动上下文中隐藏。

UI 使用生成的 Orval hooks 处理对话元数据和生命周期，并使用一个小的
`agent-stream.ts` 客户端处理 `text/event-stream`，因为生成的 hooks
解析普通 JSON 响应。Markdown 使用 `skipHtml` 渲染；引用会解析到
文件库预览或记忆阅读器。已保存的问题仍可在 `/questions` 用于后续
agent 轮次。

导航栏是分组的，而不是扁平的。档案工作区排在最前（聊天、文件库、
时间线、搜索、仪表盘；记忆是文件库的“记忆”标签页），然后是包含 **用户资料** 的个人区块，
接着是系统区块（设置、**更改密码**、仅 root 账户可见的 **账户**、
关于），以及一个单独的 **会话** 区块，包含 **登出**。页脚身份也是
root 用户切换器：root 点击它会打开可搜索的账户对话框，而普通账户
看到的是普通身份块。在模拟期间，页脚保留目标账户和一个小型
**查看身份** 标记，页面画布上方有一条持久横幅，指明目标并提供
**返回 root**，它会在结束会话前要求输入 root 密码。索引编号根据
渲染位置计算，因此对普通用户隐藏账户和切换器不会留下空隙。root 的
`/` 会打开聊天；档案摘要位于 `/dashboard`，使用 `database` 导航栏
图标。低于 980 px 时，导航栏变成从移动栏打开的导航抽屉。

### 聊天工作区

`/chat` 是一个固定高度的三栏工作区：可折叠的对话抽屉、流列和工具
检查器。一条 12 px 分隔条支持指针拖动、点击折叠，以及键盘
方向键/Home/End；比例和折叠状态在本地持久化。低于 900 px 时，
检查器变成标签页。输入框在 Enter 时发送，在 Shift+Enter 时插入
换行，并在流式传输时提供停止。

没有第二个输入框。之前的浮动停靠区和命令面板已被移除；已保存的
问题像任何其他轮次一样通过 `/chat` 运行。

状态气泡描述可观察的工作，而不是隐藏的思维链：定位、搜索、阅读、
比较、撰写、保存、封存和错误。每一行可以显示步骤、工具名称、
经过时间、状态和简短的结果摘要。

检查器会把用户正在阅读的资源保留在屏幕上。它会跟随最新的工具调用，
直到用户固定某个面板；它提供 **跟随当前** 以恢复跟随，并在后续工具
没有资源时保留最后一个有效资源。检查器面板复用与文件库和记忆阅读器
相同的安全渲染器和文件/记忆查询，而不是增加第二条渲染路径。

| 工具 | 检查器构想 |
|---|---|
| `search_knowledge` | 跨文件、记忆和摘要的结果星座；摘录就地展开 |
| `read_file` | 带有文件 id、分块编号和引用的手稿分块窗口 |
| `read_timeline` | 带有密度、采样事件和跳过计数的时间带 |
| `read_path` | 可直接打开文件夹或文件的文件夹分支图 |
| `read_memory` | 带有取代邻居的压制叶片记忆链 |
| `save_memory` | 带有状态、记忆 id 和被取代 id 的火漆封印回执 |
| `present_resource` | 嵌入文件或记忆查看器的展示台 |

每个面板都提供加载、空、错误和成功状态。工具结果 `data` 携带使
这些面板成为可能的有界、仅 UI 的摘录和查看器 URL；面向提供商的
工具内容保持不变。

聊天检查器、文件库工作区和文件夹面板已在当前版本中实现。生产客户端会在
Docker 镜像内从 `frontend/` 编译，因此修改前端后只需重新构建镜像。

### 资源预览

文件在文件库内的就地预览模态框中打开；记忆位于文件库的“记忆”标签页，
阅读器在 `/library/memories/:id`，并有一个按已存储的嵌入、共同关键词和共同
摘要排序的“关联记忆”分区。旧的 `/memory/*` 和 `/viewer/*` URL 会重定向到
这些界面，因此旧引用和书签仍然有效。

| 资源 | 渲染器 |
|---|---|
| PDF | `react-pdf` 11 + 捆绑的 `pdfjs-dist` 6，页面导航、缩放、适应宽度、文本层 |
| DOCX | 脚本禁用沙箱中的 `docx-preview` |
| PPTX | `pptxviewjs` Canvas 渲染器，支持幻灯片导航和键盘方向键 |
| 电子表格（XLSX/XLS/XLSM/ODS） | 延迟加载的 SheetJS 网格、工作表标签、隐藏标记、冻结表头，以及 500 × 50 的受限预览 |
| 图像 | 使用标准文件内容端点的原生图像 |
| 文本 / JSON / Markdown / CSV | 带换行/复制/下载的档案页，美化 JSON，GFM Markdown |
| 记忆 | 带有谱系和追溯链接的压制记录式记忆叶 |

`GET /api/v1/files/{file_id}/content` 以内联方式提供原始文件，带有
`nosniff`、沙箱 CSP、ETag/Last-Modified，以及单范围 HTTP Range 支持
（`206`/`416`；`If-None-Match` 返回 `304`）。`/download` 仍然是
附件。旧的纯文本记录具有 `has_original=false`；页面会完全跳过
`/content` 探测，并读取已索引的分块。

每个上传的图像、PDF，以及内嵌预览图的 Office 文件，也会在摄取时生成一张
极小的 WebP 缩略图（`GET /api/v1/files/{file_id}/thumbnail`）。文件库卡片、
媒体网格、聊天资源卡片和预览加载状态，都会先在按已知尺寸预留的框内绘制
缩略图，因此完整预览加载时不会跳动或闪烁。摄取 worker 会为较早上传的文件
回填缩略图（`APSOR_THUMBNAIL_BACKFILL_ENABLED`，默认开启）。

PDF.js 的 CMaps 和标准字体由 `bun run pdf-assets` 从固定版本的
`pdfjs-dist` 包复制到 `frontend/public/pdfjs/`，`dev` 和 `build` 会
自动运行它。Vite 会在构建镜像时把它们输出到 `frontend/dist/pdfjs/`，
因此会与其余产物一起打包。它们在本地提供，永远不会从 CDN 获取。

### 账户、角色与会话

首次访问时，应用会要求你创建 root 账户。没有默认密码，也没有电子
邮件恢复。root 随后可以从 **账户** 创建普通账户；新账户会使用生成
的 20 字符临时密码创建，该密码只显示一次，并且它必须在加载任何
档案内容之前选择新密码。新账户还会继承部署的主要聊天端点与模型，
因此聊天和后台 AI 可立即使用；如果部署没有活动聊天端点，账户会保持
未分配。root 可以禁用、启用、重置和模拟其他账户。
禁用账户或重置其密码会撤销其会话；撤销在请求开始时检查，因此已经
在流式传输的 SSE 轮次可能会完成其当前运行。账户永远不会被删除，
因此用户名会一直保留。

**账户** 现在使用更大的信息卡片。每张卡片包含头像、名称和
`@username`、角色/状态徽标、创建日期、最近登录，以及该账户汇总的
agent 用量：总令牌、提示词令牌、补全令牌和缓存令牌、API 调用、轮次以及最近
活动。提示词/补全的拆分绘制成一个小条，没有 agent 活动的账户仍会
显示可读的零状态。用量按 agent 运行计数，并由数据库触发器汇总，
因此卡片仍然是一次廉价的 root 专用列表读取，而不是跨账户对话扫描。

每张卡片还会汇总该账户的模型分配。root 会在令牌配额旁打开 **模型**，
分配主端点和辅助端点、其自由文本模型与力度，以及可选的上下文预算，或
重置两个槽位。账户本身会在 **设置 → 模型** 以只读方式看到同样的两个
槽位；只有 root 可以更改它们。

root 可以从页脚用户切换器或从普通活动账户卡片启动模拟会话。对话框
会在仅 root 可见的账户列表中本地搜索，排除 root 账户，并拒绝已禁用
或必须更改密码的账户。模拟是刻意的受信任 root 能力：cookie 变成
目标账户的会话，并带有 `impersonator_user_id` 标记，目标账户的角色
控制每个普通授权决定，仅 root 可见的页面消失。持久横幅会指明目标，
并提供 **返回 root**，它要求输入 root 密码、删除模拟会话并签发新的
root 会话。要求密码可以防止被模拟的人接管 root。模拟期间会拒绝
更改密码。一个标签页中的会话转换会重新加载其他标签页，因此过期的
DOM、草稿、对话框和账户范围的查询行无法存活；最近聊天恢复指针也会
被清除。这不是 RLS 绕过；它是最受信任账户以他人身份行动的另一种
方式，就像重置他们的密码一样。

两种角色使用相同的私有档案界面。root 额外管理账户和全局设置，但
不是数据超级用户：API 和 PostgreSQL 行级安全阻止它通过普通查询读取
另一个账户的文件、记忆或对话。密码重置和显式模拟是受信任恢复的
例外：root 可以签发临时密码或打开目标账户的会话，因此可能以该账户
身份登录。请相应地保护 root 凭据；RLS 并不是针对恶意 root 使用这些
能力的防御。普通用户看不到全局设置标签或 **账户** 页面；他们的设置
只显示 **常用提示词**、**模型** 和 **语言**，而 root 看到全部九个标签。
仪表盘和统计计数限定在登录账户内；AI 状态是部署级运行时诊断，而不是
账户的模型分配。密码使用 Argon2
哈希；数据库只存储每个会话令牌的 SHA-256 哈希。cookie 是 HttpOnly、
SameSite=Lax，并在 `APSOR_COOKIE_SECURE=true` 时启用 Secure
（Cloudflare compose 会设置它）。每个账户可以在 `/profile` 编辑其
显示名称和任意数量的有序标题/内容个人资料卡；名称会标注聊天轮次，
卡片会作为 `user_profile` 系统区段冻结到新对话中。登录用户名保持
不可变。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/auth/status` | 首次运行状态和当前会话 |
| `POST` | `/api/v1/auth/setup` | 创建 root 账户（仅首次运行） |
| `POST` | `/api/v1/auth/login` | 校验密码并设置会话 cookie |
| `POST` | `/api/v1/auth/logout` | 删除会话并清除 cookie |
| `POST` | `/api/v1/auth/password` | 更改登录用户的密码；在强制更改期间允许 |
| `GET` | `/api/v1/auth/me` | 当前账户（需要会话） |
| `GET` | `/api/v1/auth/profile` | 显示名称加上每张有序个人资料卡 |
| `PUT` | `/api/v1/auth/profile` | 原子地替换显示名称和所有卡片 |
| `GET` | `/api/v1/accounts` | 列出每个账户，root 在前（仅 root） |
| `POST` | `/api/v1/accounts` | 创建普通账户并返回一次性临时密码（仅 root） |
| `POST` | `/api/v1/accounts/{user_id}/disable` | 禁用账户并撤销其会话（仅 root） |
| `POST` | `/api/v1/accounts/{user_id}/enable` | 重新启用账户（仅 root） |
| `POST` | `/api/v1/accounts/{user_id}/reset-password` | 替换另一个账户的密码（仅 root） |
| `POST` | `/api/v1/accounts/{user_id}/impersonate` | 把 root cookie 替换为普通目标账户会话（仅 root） |
| `POST` | `/api/v1/auth/impersonation/stop` | 校验 root 密码、删除模拟会话并签发新的 root 会话 |

每个知识、设置、提示词和 agent 端点都要求已登录的活动账户。仅 root
的设置和账户路由对普通用户返回 `403 forbidden`，带有
`must_change_password=true` 的会话在更改密码之前只能访问认证状态、
更改密码和登出端点。只有 `/api/v1/health`、`/health`、
`/api/v1/auth/status`、`/api/v1/auth/setup`、`/api/v1/auth/login`、
`/api/v1/auth/logout`、`/api/docs`、`/api/redoc`、`/openapi.json` 和
SPA 外壳是公开的。工具端点也需要会话 cookie。

文档摄取（`POST /api/v1/files`）支持：

- **图像**（`jpg`、`jpeg`、`png`、`webp`）— 配置后使用 DeepSeek 视觉
  提取：原文语言的 OCR 文本、GitHub-Flavored Markdown 表格，以及以所设
  描述语言撰写的完整视觉描述。否则使用由文件名派生的说明文字，并带有
  `extraction_method=filename`。图像仍然是普通的文件库文件。
- **PDF** — 先使用 pypdf 文本；当文本为空、乱码，或 AI 结构化分析
  表示 `use_vision` 时，使用 pypdfium2 渲染最多 10 页并运行文档页模式
  视觉提取：OCR、表格和简短版面说明。
- **DOCX** — python-docx 段落和表格；嵌入图像可以提供视觉回退，并使用
  完整图像模式的描述和表格。
- **PPTX** — python-pptx 幻灯片文本框、表格、组合形状和演讲者备注；嵌入的
  `ppt/media` 图像可以提供视觉回退，并使用完整图像模式的描述和表格。不支持
  旧版二进制 `.ppt`。
- **XLSX / XLS / XLSM / ODS** — python-calamine 按顺序读取工作表，包含隐藏
  工作表和合并单元格，并把每个工作表渲染成 GitHub-Flavored Markdown 表格。
  优先使用公式缓存值；对于 OOXML 工作簿，openpyxl 会在生成的文件没有缓存
  结果时补回公式文本。上限为每个工作表 10,000 行、100 列、每个单元格 4,000
  个字符，以及会根据 500 分块上限自动下调的工作簿文本预算；截断会留下明确
  标记。电子表格提取只使用文本，永远不使用视觉流程。

每个视觉提取的文件都会记录 `vision_prompt_sha256`、`vision_prompt_mode`
（`image` 或 `document`）和 `vision_description_language`；旧行保持
`null`，表示未记录提示词。自定义提示词只会应用于未来的摄取。若要基于
已存储的原始文件创建新版本，请使用上文的重新摄取路由；文本文件不符合
条件，而没有嵌入图像的 DOCX 或 PPTX 会保留纯文本结果，不记录提示词指纹。

相同的摄取可通过 `POST /api/v1/files/async` 和
`POST /api/v1/files/text/async` 异步使用；轮询
`GET /api/v1/files/ingest-jobs/{id}` 获取阶段和分块进度。见上文的
**摄取运行时**。

交互式文档：<http://127.0.0.1:8000/api/docs>。OpenAPI 架构是已提交的
Orval 客户端的来源。
