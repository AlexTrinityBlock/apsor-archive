# 系统架构

[English](../architecture.md) · [繁體中文](../zh-TW/architecture.md) · **简体中文**

## 技术栈

| 层 | 选择 |
|---|---|
| API | Python 3.13、FastAPI、SQLAlchemy 2 async、Alembic、psycopg 3 |
| 存储 | PostgreSQL 17（`pg_trgm` 用于路径模糊搜索）；原始字节位于 RustFS（默认）、Cloudflare R2、任何 S3 兼容存储桶或本地磁盘 |
| 缓存 | Valkey / Redis 兼容，带内存回退 |
| 检索 | CJK 二元组 + 拉丁词元 n-gram、BM25、带符号哈希向量、RRF |
| AI | DeepSeek `deepseek-flash`、Anthropic Claude，或任何 OpenAI 兼容的聊天端点 |
| 前端 | React 19、TypeScript、Vite、React Router、React Query、Orval |
| 部署 | Docker Compose（Caddy + Cloudflare Tunnel），或使用 `uv` 的裸机 |

## 检索如何工作

1. **规范化**：使用 NFKC 并转为小写。标点变成空白。
2. **索引** 重叠的 CJK 二元组、拉丁词和拉丁三元组。每个分块存储
   一个唯一的 n-gram 列表及其词频。
3. **BM25** 对候选打分（`k1=1.2`、`b=0.75`）。像
   `automobile ford` 这样的并集查询会自然偏向同时包含两个词的分块。
4. **向量召回** 默认使用 384 维的带符号特征哈希嵌入器，因此可以
   离线工作。设置 `APSOR_EMBEDDING_PROVIDER=openai` 以及匹配的基础
   URL/模型，即可改用托管的嵌入模型。
5. **融合**：使用倒数排名融合。每种档案来源类型保留自己的顶部
   `result_number`，因此摘要不会被文件分块挤掉。
6. **去重**：按分块 id 去重，然后填充文件、记忆或摘要行。
7. **对话历史**：走另一条扁平索引通道。每条超过 256 字符的用户或 assistant
   消息会被切成 256 字符、32 字符重叠（步幅 224）的窗口。查询嵌入按余弦
   相似度取前 128 个窗口；BM25 为每个召回的窗口评分；倒数排名融合会重新排序
   并集，并保留前 15 名。无论档案历史开关如何，历史窗口始终纳入。每个命中都
   带有稳定的 `agent_entry` id，Agent 会用 `history_message` 展开它。已删除的
   对话会被标记为非当前，并从这条通道消失。

如果向量召回不可用，搜索仍然返回 BM25 结果。嵌入失败绝不会丢失段落：
当提供方额度用完（例如 OpenAI 的 `insufficient_quota`）、拒绝密钥、无法连接，
或账号的嵌入用量额度已用完时，每一条摄取路径（持久化 worker 任务、同步文本、
Markdown 编辑、记忆、摘要和对话历史）仍会保存分块的文本和 n-gram，让关键词
搜索立即能找到，并把向量标为*待补*（`embedding IS NULL`）。专用 worker 的
`EmbeddingBackfill` 循环（`APSOR_EMBEDDING_BACKFILL_ENABLED`，默认开启）会自动
补上待补的向量：

- 提供方错误（计费、额度、认证、速率限制、服务中断）会让循环以指数退避暂停，
  最长 30 分钟，而且不会算到段落头上。退避结束后会自动恢复；嵌入提供方配置
  变更时，或 root 在充值后于系统通知按下**立即重试**时，会立即恢复。
- 嵌入用量额度已用完的账号会先跳过，直到 root 提高额度或周期重置；补嵌入
  和其他嵌入一样会记录用量。
- 被提供方以输入错误拒绝的段落（HTTP 400/413/422）会单独重试，最多五次，
  之后只保留关键词搜索。

root 可以在系统通知中看到待补数量、worker 状态和下次重试时间
（`GET /api/v1/system/embedding-backfill`；`POST
/api/v1/system/embedding-backfill/retry`）。只有在持久化任务进行中，提供方
重新加载后会改变模型或维度时，该任务才会失败，避免同一个文件混用两种向量空间。

### 我需要嵌入模型密钥吗？

不需要。默认的带符号特征哈希嵌入器离线运行，并提供真正的词法向量
召回。基于 CJK 二元组的 BM25 处理精确术语和人名。如果你想要语义或
跨语言召回，请把服务指向 OpenAI 兼容的嵌入端点：

```bash
mkdir -p .secrets
cat > .secrets/openai.env <<'EOF'
APSOR_EMBEDDING_PROVIDER=openai
APSOR_EMBEDDING_BASE_URL=https://api.openai.com/v1
APSOR_EMBEDDING_MODEL=text-embedding-3-small
APSOR_EMBEDDING_DIMENSION=1536
APSOR_EMBEDDING_API_KEY=sk-...
EOF
chmod 755 .secrets
sudo chgrp 10001 .secrets/openai.env
chmod 640 .secrets/openai.env
```

设置页面也可以把此配置存储在数据库中。更改嵌入模型后，打开设置并
运行 **重新嵌入文件库**（或调用
`POST /api/v1/settings/providers/embedding/reindex`），以便现有分块
获得新维度的向量。在此之前，文本搜索仍然有效，向量搜索会跳过不
兼容的分块。

### 什么是带符号哈希嵌入器？

它是一种确定性的特征哈希向量化器，而不是训练过的神经网络模型。
每个词元（CJK 二元组、拉丁词或拉丁三元组）都会用 BLAKE2b 哈希到
384 个桶之一。摘要的一位成为符号，因此冲突会部分抵消，而不是总是
累加。桶值会被累加，向量会进行 L2 归一化。

```text
token -> BLAKE2b -> bucket 0..383 + sign(+1/-1) -> accumulate -> normalize
```

结果：

- **没有模型下载、没有 GPU、没有密钥。** 它在 CPU 上运行，每个
  分块只需微秒级时间，每个向量只需几 KB 内存。
- **是词法的，不是语义的。** `car` 和 `automobile` 是不同的词元。
  BM25 处理精确术语，但查询措辞很重要。
- **确定性的。** 相同的文本总是产生相同的向量，这使得摄取和测试
  可复现。
- **在个人规模下进行精确扫描。** 当前实现最多扫描 20,000 个当前
  向量，并在 Python 中计算余弦。在更大的语料上，请用 pgvector/HNSW
  或托管的嵌入模型替换它；`EmbedderProtocol` 边界保持不变。

## 数据模型

架构遵循三条规则：源元数据存放在其所属表中，统一的分块表只存储
源键，每条私有行恰好携带一个所有者。

```text
file ─────────────┐
folder ───────────┤
memory ───────────┼──> chunk ──> chunk_ngram
memory_summary ───┤
agent_entry ──────┘  (source_kind = history)
```

下面的私有档案表携带 `user_id bigint NOT NULL`。例外是全局配置表
（`agent_config`、`ingest_config`、`system_prompt_section` 和四张
提供商表），它们是共享部署配置；以及认证表（`app_user`、
`user_session`），它们保存身份而不是档案内容。私有表中的父/子链接
使用复合 `(id, user_id)` 外键，因此一行无法指向另一个账户的谱系。
`apsor_app` 角色上的强制 PostgreSQL 行级安全是数据库兜底；请求事务
在一个事务期间设置 `app.user_id`。认证表刻意留在 RLS 之外，因为
登录和会话查找发生在用户上下文存在之前；全局配置表是读全部/root 写。

- `file`：每个版本一行。`is_current` 和 `deleted_at` 是软状态；id
  永远不会被复用。文件叶不会在文件夹表中重复：它们的位置是
  `raw_file_path`。`storage_backend` 记录原始字节的 `local`、`r2` 或 `s3`，
  并且当且仅当 `storage_key` 为 null 时为 null。
- `folder`：显式的文件夹记录（`parent_id`、`path`、`name`、
  `depth`）。空文件夹和文件夹身份独立于文件而存在。唯一性按账户：
  `(user_id, path)`。
- `chunk`：`(source_kind, source_id, chunk_index)`，带有一个可选的
  JSONB 向量。`source_kind` 是 `file`、`memory`、`summary` 或 `history`；
  历史分块的 `source_id` 是不可变的 `agent_entry` id，内容是一个原始的
  256 字符窗口。
- `chunk_ngram`：BM25 使用的倒排索引。
- `memory`：线性时间线，带有自动生成的 `title`、`supersedes_ids`、
  `superseded_by_id`、`status=active|deprecated`，以及直接停用的来源
  信息 `deprecated_at` / `deprecated_reason`。已弃用的行必须有一个
  后继者或一个 `deprecated_at` 时间戳。
- `memory_summary`：周期、源记忆 id、主题、生成器和模型。
- `chat_provider_config` / `embedding_provider_config` /
  `web_search_provider_config` / `web_fetch_provider_config`：每个
  已保存提供商一行，带有加密的 API 密钥、安全提示，以及模型/基础
  URL/维度。`chat_provider_config` 还存储可选的 `max_output_tokens`，
  并接受 `anthropic`、`deepseek`、`openai-compatible` 和 `none`；聊天行
  是账户所分配的端点。`is_active` 上的部分唯一索引强制每种能力只有一行
  活动记录。`web_search` 和 `web_fetch` 是独立的凭据。
- `app_user`：每个账户一行。`role` 是 `root` 或 `user`；`is_active`、
  `must_change_password`、`disabled_at`、`created_by_user_id` 以及
  密码审计时间戳描述账户生命周期。八个分配字段是
  `chat_provider_config_id`、`chat_model`、`chat_reasoning_effort`、
  `aux_provider_config_id`、`aux_model`、`aux_reasoning_effort`（非空，
  默认 `low`）、`chat_context_window_tokens` 和
  `chat_compaction_threshold_tokens`。部分唯一索引强制恰好一个 root，
  用户名保持全局唯一且不可变。
- `user_profile_card`：描述账户的有序标题/内容卡片；完整集合会作为
  `user_profile` 区段冻结到新对话中。
- `frequently_used_prompt`：用于空聊天页面的私有、账户可编辑快捷
  方式，按 `sort_order` 排序，每个账户最多 20 行。
- `agent_conversation` / `agent_entry` / `agent_run`：持久化 agent 的
  对话记录范围、不可变条目日志和每次提交的运行状态。
  `agent_commit_seq` 对在一个事务中写入的条目进行分组。页面快照是
  同一日志中的 `pi.page-context` 条目，而不是单独的表。
- `agent_approval`：针对需要确认的写入的持久化待处理/已批准/已拒绝/
  已过期人工决定，带有经过校验的参数、安全预览，以及用于恢复等待
  运行的循环快照。
- `agent_config`：一行（`id=1`），带有 agent 循环和设置 API 使用的
  经过校验的运行时限制，包括压缩模板与输出上限，以及升级开关。
- `saved_question`：账户的问答库。`question` 由用户撰写；`answer`、
  `citations`、`conversation_id` 以及运行状态/错误字段只由提问写入。
  `conversation_id` 使用 `ON DELETE SET NULL`，`last_asked_at` 记录
  最近一次尝试。
- `file_ingest_job`：持久化摄取队列。它存储源类型、路径、负载键和
  后端、状态/阶段、`progress_pct`、分块计数、有界错误字段以及尝试/
  时间戳。每个账户的一条路径只能有一个活动任务。任务指向其暂存
  文件，失败时清除该链接，并且只有任务发布文件时，文件及其分块才会
  成为当前。
- `file_thumbnail`：每个文件版本一张极小的 WebP，以 `file_id` 为键，带有
  `status`（`ready`、`none` 或 `failed`）、像素尺寸、SHA-256、生成器版本和
  尝试次数。它会随其文件一起级联删除。
- `companion` / `companion_frame` / `companion_preference`：账户的自定义聊天
  伙伴、每个动作经编码的 AVIF（或 WebP）帧及其位置、大小和 SHA-256，以及账户
  的伙伴选择、是否显示、动态程度和位置。
- `companion_story` / `companion_lore_fragment` / `companion_bond`：账户按语言
  覆写的伙伴人设与传说、其片段，以及解锁更深层传说的完成对话数。
- `ingest_config`：一行（`id=1`），带有经过校验的 worker 轮询、
  提取、在途、嵌入和分块大小设置。它不是分块来源；队列引用最终
  发布的文件。

原始字节不存储在 PostgreSQL 中。它们位于本地磁盘、私有 R2 存储桶，或
S3 兼容存储桶（默认为 RustFS）中，由每个文件的 `storage_backend` 选择；提取的分块及其 n-gram
保留在 PostgreSQL 中。

代码、注释和文档以英语编写，英语为规范版本。界面和本 README 也提供完整的
繁体中文与简体中文翻译，并与英文源一起更新。
