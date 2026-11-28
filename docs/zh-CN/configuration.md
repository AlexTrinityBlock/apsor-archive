# 配置

[English](../configuration.md) · [繁體中文](../zh-TW/configuration.md) · **简体中文**

### 在应用中配置提供商

设置页面是配置提供商的标准方式，且只有 root 账户能编辑全局注册表。它会写入
四张相互独立的能力表，因此一种能力永远不会覆盖另一种：

- **聊天** —— `chat_provider_config`：DeepSeek、Anthropic Claude 或任何
  OpenAI 兼容的聊天端点。聊天行是账户所分配的 **端点**；它有可选的
  `max_output_tokens` 上限（256–131,072）。
- **嵌入** —— `embedding_provider_config`：离线的 `hashing`、`openai` 或
  `openai-compatible`。多行可以组成一条链，但每个活动行都必须使用相同的
  模型和维度。
- **网页搜索** —— `web_search_provider_config`：Tavily、Exa 或 DeepSeek。
  多行可以同时处于活动状态，组成一条有序的链。
- **网页抓取** —— `web_fetch_provider_config`：Tavily `extract`、Exa
  `contents` 或 DeepSeek `fetch`。网页搜索和网页抓取被刻意分为不同的行，
  因此它们可以使用不同的提供商或不同的凭据。

每张表都存储从零开始的 `priority`，并对 `priority WHERE is_active` 设有部分
唯一索引。对嵌入、网页搜索和网页抓取而言，链中的第一行是主行，其余是备用；
只有在提供商或传输失败时才会前进到下一行，且所有行都失败后操作才失败。
聊天不同：每个账户被分配到一个确切的聊天行，Agent 轮次永远不会故障转移到
另一个聊天行。嵌入备用必须与主行共享模型和维度，因为混合向量空间会损坏
每个所有者的索引。删除一行不会复用其身份 ID。

提供商行属于全局部署配置：只有 root 账户可以列出、编辑、测试或删除它们，
普通用户永远不会收到提供商机密或全局运行时设置。API 从不返回明文密钥：
浏览器只会收到诸如 `...14f8` 的提示。`APSOR_SECRET_KEY` 提供 Fernet 主密钥。
如果未设置，会在 `data/.secret_key`（Docker 中为 `/data/.secret_key`）创建
权限为 `0600` 的密钥文件，因此加密值能在重启后保留。`APSOR_TAVILY_API_KEY`
是两种网页能力可选的环境回退。Exa 密钥可以放在被 gitignore 的
`.secrets/exa.env` 中，名为 `EXA_API_KEY`（或 `APSOR_EXA_API_KEY`）；加密的
提供商行仍然优先。聊天所用的同一个 `APSOR_DEEPSEEK_API_KEY` 也是 DeepSeek
网页搜索和网页抓取提供商的环境回退，因此不需要单独的网页凭据。Anthropic
密钥可以放在 `.secrets/anthropic.env` 中，名为 `ANTHROPIC_API_KEY`（或
`APSOR_ANTHROPIC_API_KEY`）；端点行上的数据库密钥仍然优先。

聊天端点拥有其密钥，而不是账户。多个账户可以共享一个端点，轮换或清除该端点
的密钥会影响分配到它的每个账户。没有加密密钥的行可以使用提供商范围的环境
密钥作为行补充，但不存在每用户密钥，也不存在部署全局的聊天回退：未分配的
账户永远不会被另一个活动行或单独的环境密钥挽救。

嵌入、网页搜索和网页抓取的优先顺序为：**活动的数据库链 → 环境 → 内置
默认值**。就聊天而言，账户分配按 ID 选择端点行；提供商范围的环境密钥只能
补全该行。设置页面会标注每个提供商的来源并显示链的顺序。更改嵌入模型不会
重写现有向量；`reindex_required` 会发出警告。请运行 **重新嵌入文件库**（或
`POST /api/v1/settings/providers/embedding/reindex`）来刷新当前分块。向量
搜索会跳过维度与当前嵌入器不匹配的分块。

提供商注册表 API：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/settings/providers` | 四个能力组、掩码提示、有序的链、重建索引建议 |
| `POST` | `/api/v1/settings/providers/{capability}` | 创建一个已保存的提供商；可选择将其追加到链中 |
| `PUT` | `/api/v1/settings/providers/{capability}/{provider_id}` | 替换一个已保存的提供商，不重新排序链 |
| `DELETE` | `/api/v1/settings/providers/{capability}/{provider_id}` | 删除一个已保存的提供商并填补链中的空缺 |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/activate` | 追加该行，或传入 `priority=0` 使其成为主行 |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/deactivate` | 从链中移除一行并填补空缺 |
| `POST` | `/api/v1/settings/providers/{capability}/deactivate` | 清空整条链；嵌入／网页回退到环境／默认值，聊天分配变为未启用 |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/test` | 发送一个小型提供商请求并测量延迟 |
| `POST` | `/api/v1/settings/providers/embedding/reindex` | 用活动提供商重新嵌入每个当前分块 |

`{capability}` 是 `chat`、`embedding`、`web_search` 或 `web_fetch` 之一。
注册表响应会在 `providers` 缓存范围下缓存 30 秒；每次提供商写入都会刷新该
范围。

当整条链都失败时，API 和 worker 会记录一条经过清理的 `provider_error_notice`
行，root 会在账户页面看到它。通知会在 15 分钟的窗口内按能力、操作和错误代码
去重；重复发生时 `count` 和 `last_seen_at` 会前进。这张表只保存提供商元数据，
绝不保存提示词或档案内容。root 可以列出通知、解决单条通知，或全部解决：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/system/provider-notices?status=open\|all&limit=50` | 未解决的通知与未解决数量 |
| `POST` | `/api/v1/system/provider-notices/{notice_id}/resolve` | 解决一条通知 |
| `POST` | `/api/v1/system/provider-notices/resolve-all` | 解决所有未解决的通知 |

### 每个账户的模型分配

每个账户都有两个聊天槽位。**主** 槽位负责 Agent 聊天。**辅助** 槽位负责
摘要、记忆整合、摄取标题与标签、文档分析、提取以及视觉。root 从
**账户 → 模型** 分配两者：选择一个已保存的聊天端点，输入模型名称和推理
力度，设置可选的上下文预算，然后对每个连接发生变更的槽位按下 **测试**。
普通账户从 **设置 → 模型** 读取同样的两个槽位；该视图是只读的。

模型名称和力度字符串是自由文本，上限分别为 128 和 32 个字符。模型目录
只是建议，永远不是允许列表。已知模型可能会提供价格、层级和分词比例；未知
模型以 `tier=None` 接受，不进行路由、不自动升级，成本显示为 `unpriced`。
对话框中的力度提示只是提供商指引：DeepSeek 接受 `low | high | max`
（默认 `high`，并有 `minimal`→`low`、`medium`/`xhigh`→`high`、
`ultra`→`max` 别名），Anthropic 接受 `low | medium | high | xhigh | max`，
OpenAI/GPT 依模型接受 `none | minimal | low | medium | high | xhigh | max`。
探测才是验证。

端点行拥有 Fernet 加密密钥。多个账户可以共享一个端点；轮换或清除其密钥
会影响分配到该端点的每个账户。不存在每用户密钥，也不存在全局或环境聊天
回退：缺失、未激活、已禁用或没有密钥的端点会失败关闭。辅助槽位只有在
两个辅助字段都为 `NULL` 时（升级回填的形状）才继承主端点和模型；该继承
工作使用辅助力度，默认 `low`。有辅助行但没有模型，或有模型但没有行，
会报告为降级，而不是静默回退。

保存受探测门控。服务器会对每个连接指纹（端点行、基础 URL、密钥密文、
模型和力度）发生变更的槽位执行一次真实的 16 令牌生成；即使浏览器已经
按下 **测试**，`PUT` 仍会在服务器端重新检查该门控。只有预算变更时会跳过
探测。如果探测失败，请求返回 `422 model_probe_failed`，并且不写入任何
内容。删除分配会清除两个槽位，使账户保持未分配。

上下文窗口和压缩阈值是可选的每账户覆盖值；空白值继承 `agent_config` 的
部署默认值。上下文窗口是真正的对外发送输入预算，不是模型元数据。每次
提供商调用前，Agent 会估算请求，并且绝不引发本地上下文错误：超出预算
时，先按预算的 60% 强制执行确定性压缩，再丢弃页面上下文，然后从最旧的
开始把工具结果正文裁剪为 8,000、2,000、500 个字符（保留
`<tool_result>` 信封），最后只截断当前用户消息的对外副本（必要时丢弃其
附件）。一条 `ui.notice` 记录模型未看到的内容。存储的对话记录不变。不
存在 `agent_context_limit_exceeded` 代码。

压缩始终是确定性的，永不调用提供商。root 可以在 `agent_config` 编辑其
指令模板；模板必须包含 `{max_output_tokens}`，并可使用
`{max_output_chars}`、`{max_items}`、`{max_line_chars}` 和
`{max_last_user_chars}`。缺少输出上限、使用未知占位符或含有不成对大括号
的模板会返回 `422 compaction_prompt_invalid`，并且不会保存。

开启 `model_escalation_enabled` 时，Agent 每次运行最多升级一次，沿目录
上升一层，并在同一个端点上。触发条件为：经过一次压缩后仍被上下文窗口
拒绝、重试后仍未产生文本且达到输出上限、连续三次无效参数的工具调用、
无法使用的补全，或拒绝回答。5xx、超时、401/403 或配额错误永不升级。
一条 `ui.notice` 记录 `reason`、`from_model` 和 `to_model`。未知模型没有
层级，因此永不升级。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/model-assignments` | 每个账户的存储值、有效值和警告字段（仅 root） |
| `GET` | `/api/v1/model-assignments/me` | 调用者自己的分配（每个已认证账户） |
| `PUT` | `/api/v1/model-assignments/{user_id}` | 探测已变更槽位并保存两个分配（仅 root） |
| `DELETE` | `/api/v1/model-assignments/{user_id}` | 清除两个分配（仅 root） |
| `GET` | `/api/v1/chat-endpoints` | 已保存的聊天端点，只有主机名，绝不包含密钥或完整 URL |
| `POST` | `/api/v1/chat-endpoints/{provider_config_id}/probe` | 测试一个候选模型/力度；不写入任何内容 |
| `GET` | `/api/v1/model-catalog` | 按升级顺序排列的建议目录；其他模型字符串仍然合法 |

稳定的分配错误：

| 状态 | 代码 | 时机 |
|---|---|---|
| `409` | `model_not_assigned` | 账户没有主端点/模型 |
| `409` | `provider_inactive` | 分配的端点未激活、已禁用或没有密钥 |
| `422` | `invalid_model_assignment` | 端点不可用，或预算配对无效 |
| `422` | `model_probe_failed` | 已变更的槽位探测失败；未写入任何内容 |
| `422` | `compaction_prompt_invalid` | 压缩模板缺少 `{max_output_tokens}` 或含有未知占位符 |

目录价格仅供参考；现有的每账户令牌配额仍是强制执行机制，并且没有美元
成本读数。`GET /api/v1/ai/status` 仍报告部署级运行时供 root 诊断；它不是
每账户的分配。

### 网页研究工具

Agent 有两个用于外部研究的只读工具：

| 工具 | 作用 |
|---|---|
| `web_search` | 使用活动的 `web_search` 提供商搜索公共网络；返回标题、URL、可选的分数和有界摘录。 |
| `web_fetch` | 使用活动的 `web_fetch` 提供商抓取一个公共 `http(s)` URL，并返回一个由服务器定义的 Markdown 页面。 |

已实现的适配器有 Tavily（`/search` 和 `/extract`）、Exa（`/search` 和
`/contents`）以及 DeepSeek（`/v1/tools/search` 和 `/v1/tools/fetch`）。提供商
接缝是一个协议，因此可以在不更改工具层的情况下加入另一个搜索或抓取 API。
搜索结果在 `providers` 缓存作用域下缓存 15 分钟；写入提供商会使其
失效。`web_fetch` 会拒绝非 HTTP(S)、URL 中的凭据、
`localhost`/`.local`/`.internal`，以及私有或特殊用途的 IP 字面量。

`web_fetch` 会为每个 URL 缓存完整的提取文档一小时，因此翻页永远
不会再次调用提供商。结构可疑的提取结果（标题后紧跟同级或更高级的标题，或
文档以标题结尾）不会被缓存，因此之后的页面请求会重新查询提供商，而不是
固定住不完整的文档。最后一页的页脚会写着 `End of extracted content.`，并在
某个标题到下一个标题之间没有正文时附加警告。它面向模型的参数只有 `url` 和 `page`
（从 1 开始，默认 1）。服务器会把每一行源文本硬换行到 800 字符，
并把整行装入最多 12,000 字符的页面（或者更小的已配置
`web_fetch_max_chars`，绝不低于 801），因此一页永远不会超出预算，
并且始终至少包含一行。没有需要计数的行号，也没有需要计算的偏移量：
调用 `page=1`，然后 `page=2`，依此类推，直到 `has_more=false`。
每个结果都会报告 `page`/`total_pages`、`page_chars`、
`total_chars`、`has_more`、`next_page` 和 `source_truncated`，
正文以纯文本页脚结尾，例如：

```text
[web_fetch: page 1/2. More content: call web_fetch again with page=2.]
```

只要 `has_more=true`，`next_page` 就是精确的。把所有页面拼接起来会
恰好覆盖缓存文档一次，没有缺口或重叠。规范化后的完整文档上限为
2,000,000 字符；超出部分会被截断并置 `source_truncated=true`，
因此最后一页的页脚会说明源已被截断。两个工具都返回携带
`provider`、`retrieved_at`、`cached` 和 `truncated` 的 XML，
并且 Agent 被指示引用 URL 和检索时间。

对话在创建时会冻结其工具快照，因此较早的对话会保留之前的
`web_fetch` 架构。旧的 `offset`、`limit` 和 `max_chars` 参数仍会被
接受，但对面向模型的架构隐藏；它们的存在只是为了让冻结在
`archive-tools-v4`/`v5` 上的对话继续通过校验。分页模式会忽略
`max_chars` 和 `limit`，而旧式 `offset` 只会选择包含该行的页面。

摘要搜索结果和时间线摘要事件会被明确标记为压缩视图：

```xml
<source kind="summary" id="12" view="compressed" memory_count="37" ...>
  <compressed_view coverage_start="..." coverage_end="..." source_memory_count="37">
    This is a compressed summary of 37 original memories, not the complete original content.
  </compressed_view>
  ...
</source>
```

Agent 会在工具结果本身中看到 `view="compressed"`、覆盖窗口和原始
记忆数量，因此不会把摘要当作完整的对话记录。

### 常用提示词

`/settings` 上的 **常用提示词** 面板编辑空 `/chat` 页面中显示的
快捷方式。该列表对登录账户私有：每一行有标题、提示词文本和
`sort_order`；每个账户最多 20 行，按 `sort_order` 再按 `id` 排序，
并在该账户的 `prompts` 缓存作用域下缓存 60 秒。点击快捷方式会把
完整的提示词文本填入输入框；它不会发送消息。API 是
`GET/POST/PUT/DELETE /api/v1/settings/frequent-prompts`。

### 聊天伙伴

> *我们永远走不了那么远。所以我们造了能走那么远的人，把我们爱过的一切都教给他们。*

六位内置图书馆员（Vellum、Atlas、Herbaria、Horologe、Nocturne、Quill）由能存续一万年的
万古瓷烧成，他们的心智并非被设计，而是从图书馆里人类写下的字句中苏醒；他们与一个人以平等的
身份一起保管每一座档案馆。他们的世界写在
[`backend/app/module/companion/lore/BIBLE.md`](../../backend/app/module/companion/lore/BIBLE.md)，
每位图书馆员各有一份角色设定（`lore/characters/`），英文正典为 `canon.json` 与
`GLOSSARY.md`，并附完整的繁体与简体中文译本与共用术语表（`lore/zh-*/TERMS.md`）。

一位小巧的图书馆员可以自由地站在聊天旁（没有提线，也没有操纵杆）并回应 Agent：模型推理时它会思考，执行
`search_knowledge` 时会搜索，在对应的工具期间会阅读、书写、计算、浏览和展示；
Agent 也可以调用只读的 `companion_action` 工具做出明确的手势。内置角色随前端
一起发布。每个账户还可以创建最多 20 个私有自定义伙伴，每个动作最多上传 12 张
图像（PNG、JPEG、WebP 或 AVIF，每张最多 8 MB）；服务器会把每张图像重新编码为
符合 384x576 和 40 KB 的 AVIF（只有在无法使用 AVIF 编码器时才用 WebP），并移除
其元数据。每个账户的偏好会存储所选的伙伴（`preset:<id>` 或 `custom:<id>`）、
是否显示、动态程度（`full`、`reduced`、`off`）、显示大小（`compact`、`medium`、
`full`；完整大小最多以 384x576 显示，只在窗口或聊天旁的空间不足时缩小）、透明度
模式（`opaque`、`translucent`，或只在与页面重叠、你输入或滚动时变淡的 `auto`）
以及归一化的位置。每个账户都在侧栏个人区的 **伙伴** 页面（`/companion`）设置这些，
故事编辑与自定义伙伴也在这里；旧的 `/settings#settings-companion` 链接会跳转过去。API 位于
`/api/v1/companions` 之下（列出、创建、更新、删除、上传帧、帧排序、删除帧、
帧图像，以及 `GET/PATCH /api/v1/companions/preference`）。

每个伙伴也有自己的故事：一段人设，会成为它在新对话中的声音（每个对话冻结，
使用该对话的语言），以及传说，也就是它自己的记忆。Agent 搜索用户的档案馆时，
最多两段相关的图书馆员自身记忆可能会以独立区块附在结果旁；它们永远不是档案
证据，也不会被引用。询问图书馆员关于它自己或档案馆的事，它就会讲述自己的故事。
账户与该伙伴完成越多对话，越深层的记忆就会解锁。每个账户都可以按语言编辑任何
伙伴的人设与传说，并重置为默认值（`/api/v1/companions/stories/...`）。人设规则
把用户视为平等的伙伴：图书馆员会用对方的名字或直接说“你”，绝不使用馆主、
主人之类的称谓。

### Agent 运行时设置

`/settings` 上的 **Agent 运行时** 面板（仅 root）编辑单例
`agent_config` 行（`id=1`）。聊天端点和模型选择是每账户的分配（见
**每个账户的模型分配**）；该行包含并行工具与单条工具结果预算、部署默认的
上下文预算，以及压缩和升级控制。全部十九个运行时值都存储在 PostgreSQL 中，
无需重启即可应用于新的运行，并由每个账户共享。账户自己的上下文窗口和压缩
阈值在设置后会覆盖这些部署默认值。两个聊天图像存活时间值也由后台清理循环
从这一行读取；它们不是环境变量。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/agent/settings` | 有效配置、默认值、来源、`updated_at` |
| `PUT` | `/api/v1/agent/settings` | 完整替换；全部十九个字段都是必填 |
| `POST` | `/api/v1/agent/settings/reset` | 持久化并返回内置默认值 |

生成的操作是 `getAgentSettings`、`updateAgentSettings` 和
`resetAgentSettings`。

读取形状是 `{config, defaults, source, updated_at}`，其中 `source`
对于已存储的行是 `database`，当 API 不得不从默认值创建或修复该行时
是 `default`。`PUT` 要求完整快照：省略字段和多余字段都会被拒绝。

| 字段 | 默认值 | 范围 |
|---|---|---|
| `compaction_threshold_tokens` | 75,000 | 1,000–1,000,000；低于上下文窗口 |
| `context_window_tokens` | 1,000,000 | 8,000–2,000,000；部署默认预算 |
| `max_parallel_tools` | 6 | 1–24 |
| `max_tool_result_chars` | 100,000 | 1,000–200,000 |
| `max_page_context_chars` | 6,000 | 500–50,000 |
| `max_compaction_summary_chars` | 6,000 | 1,000–20,000 |
| `max_compaction_last_user_chars` | 4,000 | 500–10,000 |
| `compaction_prompt` | 内置模板 | 1–20,000 个字符；必须包含 `{max_output_tokens}` |
| `compaction_max_output_tokens` | 2,600 | 256–16,384 |
| `model_escalation_enabled` | `true` | 布尔值 |
| `agent_max_output_tokens` | 64,000 | 256–131,072 |
| `auto_compaction_enabled` | `true` | 布尔值 |
| `parallel_tools_enabled` | `true` | 布尔值 |
| `save_memory_requires_approval` | `true` | 布尔值；`save_memory` 需要人工审批 |
| `chat_attachment_staged_ttl_hours` | 1 | 1–168；未发送上传的保留期限 |
| `chat_attachment_cleanup_interval_seconds` | 900 | 60–86,400；清理扫描间隔 |
| `max_plot_points` | 10,000 | 100–50,000；每张渲染图表的数据点数 |
| `max_plot_bytes` | 600,000 | 10,000–2,000,000；序列化后的图表大小 |
| `max_plot_nodes` | 100,000 | 1,000–500,000；每张图表的 JSON 节点数 |

Pydantic 和匹配的 PostgreSQL 检查约束会强制执行范围以及三条跨字段规则：
压缩阈值必须低于模型上下文窗口、并行宽度不得超过每轮工具调用数，且
`max_plot_nodes` 至少要等于 `max_plot_points`。压缩模板也必须能用已知占位符
渲染；字面大括号需要成对重复，缺少 `{max_output_tokens}` 或含有未知占位符时，
会以 `422 compaction_prompt_invalid` 拒绝，而不是 `400 invalid_request`。绘图
预算会应用到每个账户的 `render_plot`。应用的全局校验封装会把其他请求校验
失败映射为 `400 invalid_request`，而不是 422。

一次请求会在短生命周期的数据库会话中加载一个不可变的运行时快照。活动
的 SSE 运行会保留它启动时的快照；后续运行使用更改后的设置。后端契约描述于
`backend/README.md`。

### 摄取运行时

同步的 `POST /api/v1/files` 和 `POST /api/v1/files/text` 端点仍然
存在，但 UI 可以改为把工作加入队列。异步路由会存储负载并返回
带有 `IngestJobSchema` 的 `202`：

| 方法 | 路径 | 操作 |
|---|---|---|
| `POST` | `/api/v1/files/async` | `uploadFileAsync` |
| `POST` | `/api/v1/files/text/async` | `createTextFileAsync` |
| `GET` | `/api/v1/files/ingest-jobs?limit=&offset=` | `listIngestJobs` |
| `GET` | `/api/v1/files/ingest-jobs/{id}` | `getIngestJob` |
| `POST` | `/api/v1/files/ingest-jobs/{id}/retry` | `retryIngestJob` |
| `POST` | `/api/v1/files/{file_id}/reingest` | `reingestFile` |

任务会依次经过 `queued(0)`、`parsing(5)`、`chunking(15–20)`、
`embedding(25–90)`、`summarizing(95)` 和 `ready(100)`，或以 `failed` 结束。
`progress_pct`、`chunks_total` 和 `chunks_embedded` 是持久化的，因此重新加载
的页面可以继续相同的显示。暂存的文件和分块行只有在任务就绪时才会发布；
失败的任务保留其错误，但不会暴露任何部分的当前文件。

一个 worker 进程在空闲时每秒轮询数据库，并用
`SELECT ... FOR UPDATE SKIP LOCKED` 认领排队的行。它运行两个提取
线程、最多两个在途任务，全局异步嵌入并发为六，并批量更新进度。
崩溃后陈旧任务会被重新排队，嵌入重试是有界的。API 只会把任务加入队列，
因此请在它旁边运行 worker（本地用 `make worker`，生产环境用专用服务）。
如果改为设置 `APSOR_INGEST_WORKER_ENABLED=true`，同样的循环会在 API 进程内
运行，作为单进程的开发捷径；其默认值为 `false`。

```bash
cd backend
uv run apsor-archive worker
# or
uv run python -m app.worker
# process at most one job, then exit
uv run python -m app.worker --once
```

标准和 Cloudflare Compose 栈会把它作为专用的 `worker` 服务运行，
并在 API 上设置 `APSOR_INGEST_WORKER_ENABLED=false`，因此恰好有
一个进程拥有该队列。

#### RabbitMQ 派发

Compose 栈还会运行 `rabbitmq:4-management-alpine`，作为持久化摄取的可选
低延迟派发路径。PostgreSQL 的 `file_ingest_job` 仍是权威的任务账本：消息
只携带 `{job_id, retry_count}`，消费者会重新读取该行，用
`SELECT ... FOR UPDATE SKIP LOCKED` 认领它，并根据数据库状态做决定。重复、
迟到或丢失的消息最多只会增加延迟，永远不会成为第二个事实来源。

- API 以发布者确认（publisher confirms）把持久化 JSON 消息发布到持久的
  `apsor.ingest` direct exchange。发布路径的时限为一秒
  （`APSOR_RABBITMQ_PUBLISH_TIMEOUT_SECONDS`）；消息代理（broker）失败时只按
  异常类型记录并吞掉错误，因此上传仍会返回 `202`，任务保持 `queued`。
- worker 以 `prefetch_count=1` 和手动确认消费 `apsor.ingest.jobs`。它只会在
  `process_notified_job` 返回后才确认：worker 崩溃时投递保持未确认，
  RabbitMQ 会重新投递，任务则从其行继续或重试。
- `retry` 结果和意外的处理失败会发布到 `apsor.ingest.jobs.retry`，这是一个
  30 秒 TTL 的队列，会以死信（dead-letter）转回主队列。派发重试上限为 20 次，
  因此损坏的任务不会无限循环。
- 容器上限为 384 MB，VM 水位线为 200 MB（`docker/rabbitmq/rabbitmq.conf`）。
  管理 UI 只留在 Compose 网络内，不会发布到主机；本地演示凭据是
  `apsor` / `apsor`，在任何共享部署之前都必须通过
  `RABBITMQ_DEFAULT_USER`/`RABBITMQ_DEFAULT_PASS` 更改。
- 用 `APSOR_RABBITMQ_ENABLED=false` 停用派发。此时 API 使用空操作通知器，
  worker 仍每秒轮询 PostgreSQL，因此不会丢失任何任务。消息代理停机或通知器
  连接失败时，也适用同样的轮询回退。

`/settings` 上的 **摄取运行时** 面板（仅 root）编辑单例 `ingest_config` 行。
它是完整替换，而不是补丁，读取正文带有 `{config, defaults, source,
updated_at}` 以及“数据库／默认”标签。worker 可以跨账户认领任务，但每个解析、
分块、嵌入和发布步骤都在任务所有者的行级安全上下文中运行。

| 方法 | 路径 | 操作 |
|---|---|---|
| `GET` | `/api/v1/settings/ingest` | `getIngestSettings` |
| `PUT` | `/api/v1/settings/ingest` | `updateIngestSettings` |
| `POST` | `/api/v1/settings/ingest/reset` | `resetIngestSettings` |

| 字段 | 默认值 | 范围 |
|---|---|---|
| `poll_seconds` | 1.0 | 0.25–30 |
| `extract_workers` | 2 | 1–8 |
| `max_inflight_jobs` | 2 | 1–4 |
| `embedding_concurrency` | 6 | 1–32 |
| `chunk_target_chars` | 4,000 | 1,000–20,000 |
| `chunk_overlap_chars` | 500 | 0–5,000；须低于目标值 |
| `vision_description_language` | `English` | 1–80 个字符；自由文本 |

worker 会在每次循环和每个任务读取最新的数据库快照，因此已保存的 worker 更改
无需重启即可应用；已在运行的任务保留其快照。环境值为全新安装提供初始值，并
持续作为回退。更改分块大小只影响以后的摄取。`vision_description_language`
只控制视觉描述、说明文字、标题、摘要和标签；OCR 文本和表格单元格文本会逐字
保持原文语言。更改此设置只影响以后的摄取，现有文件保留当前的提取结果。后端
契约描述于 `backend/README.md`。

#### 视觉提示词

两个视觉系统提示词与运行时快照分开存储，因此
`PUT /settings/ingest` 和运行时重置永远不会覆盖它们。`NULL` 表示使用
内置默认值。root 可以在一次保存中读取并替换两个模板；正文是完整提示词，
可包含 `{language}` 占位符。

| 方法 | 路径 | 操作 |
|---|---|---|
| `GET` | `/api/v1/settings/ingest/vision-prompts` | `getIngestVisionPrompts` |
| `PUT` | `/api/v1/settings/ingest/vision-prompts` | `updateIngestVisionPrompts` |

读取响应会返回当前 `config`、内置 `defaults`、`source`、`updated_at`、
`max_chars`、九个必需键、模板 SHA-256 以及非阻塞性的 `warnings`。保存时
会拒绝空白或超过 32K、含控制字符，或缺少任何必需输出键的提示词（`422
invalid_vision_prompt`）。如果提示词缺少 `verbatim`、`do not translate` 或
GitHub-Flavored Markdown 措辞，响应也会带回警告。

`POST /api/v1/files/{file_id}/reingest` 接受 `{expected_version}`，为当前
且具有已存储原始文件的图像、PDF、DOCX 或 PPTX 排队执行强制视觉流程。任务只会
在提取和索引成功后创建新的文件版本；在此之前，旧版本仍是最新且可读取的。
原始字节会被共用，不会被任务复制或删除。如果路径已更改，或已有更新的上传
成为最新，任务会以 `409 ingest_source_stale` 失败，更新的文件保持最新。
