# 开发

[English](../development.md) · [繁體中文](../zh-TW/development.md) · **简体中文**

### 本地开发

```bash
# 1. PostgreSQL + Valkey
docker compose -f docker-compose.dev.yml up -d --wait

# 2. API
cd backend
uv sync
uv run alembic upgrade head
uv run apsor-archive --reload

# 3. Frontend (second terminal)
cd frontend
bun install
bun run dev
```

开发数据库是位于 `127.0.0.1:55432` 的 PostgreSQL，角色为 `apsor`，
数据库为 `apsor_archive`
（`postgresql+psycopg://apsor:apsor@127.0.0.1:55432/apsor_archive`）。
Vite 运行在 <http://127.0.0.1:5173>，并把 `/api` 代理到 API。
要构建容器所服务的客户端：

```bash
cd frontend && bun run build
```

`./start.sh` 是最短的裸机路径。先运行一次 `./start.sh setup --dev` 写出开发用
的 `.env`（默认为本地存储），之后 `./start.sh` 会在 Docker 可用时启动开发
数据库/缓存、同步后端，并在 <http://127.0.0.1:8000> 运行 API，同时启动专用的
摄取 worker；按 Ctrl+C 会同时停止两者。设置 `APSOR_START_WORKER=false` 则只
运行 API。首次裸机启动前，请先运行一次 `cd frontend && bun run build`。如果要
在本地试用 S3 路径，请在向导中选择 `rustfs`，并用
`docker compose -f docker-compose.dev.yml --profile rustfs up -d` 启动开发用的
存储服务。

在 Windows 上，`./start.sh` 需要 bash shell。`./run-local.ps1` 是
等效的 PowerShell 脚本：如果 Docker 可用，它会启动开发数据库/缓存，
同步后端，并在同一 URL 提供服务。应用自己读取 `.secrets/`，因此
脚本不会导出这些值。它还会强制使用 `SelectorEventLoop`，因为
psycopg 的异步模式拒绝 uvicorn 在 Windows 上默认选择的
`ProactorEventLoop`。

```powershell
.\run-local.ps1            # http://127.0.0.1:8000
.\run-local.ps1 -Port 8080
```

### 生成的 API 客户端与漂移

仓库同时提交 `frontend/openapi.json` 和生成的
`frontend/src/app/generated-apis-types/` 客户端。因此，全新克隆和
Docker 构建无需运行后端即可工作。要更改契约：

```bash
cd backend && uv run python -m script.export_openapi
cd ../frontend && bun run api:generate
```

要检查已提交的客户端是否与后端匹配：

```bash
make api-check
```

它会重新导出架构、重新生成客户端，并在任何差异上失败。这保留了
已提交客户端的便利性，又不会让它静默漂移。架构目前声明 79 条路径。
除非契约变更是有意的，操作 ID 保持稳定。已提交的客户端包括账户、
更改密码和仅 root 的账户操作；文件夹、移动和复制操作；页面上下文
请求/详情/条目类型契约；agent 运行时设置；对话压缩/清空操作；
已保存问题的 CRUD/提问操作；以及异步摄取任务和摄取设置操作。文件库
面板、设置面板、问题簿、账户目录和聊天工作台直接调用生成的 hooks。

### 载入真实语料

Wikipedia 加载器会走与 UI 相同的摄取路径：

```bash
cd backend
uv run python -m script.ingest_wikipedia \
  --lang en --titles Automobile Dendrochronology \
  --prefix /wikipedia/en
```

在 `/chat` 的 agent 工作台跨导入的语料提问，或者把它保存到
`/questions` 的问题库中稍后运行。

### 长文档验证

已保存问题的流程还曾针对一部长篇中文小说进行手动演练。这是一个
验证示例，不是已提交的测试夹具或测试：

- 来自 Project Gutenberg 的《紅樓夢》（Dream of the Red Chamber），
  约 2.66 MB。
- 以 4,000 字符分块、500 字符重叠摄取：268 个分块。
- 真实的 `deepseek-flash` 轮次回答了关于宝玉和黛玉的前世之债与还泪
  之誓、第一章中石头的下凡与通灵宝玉，以及宝玉随僧道离去的结局等
  问题。
- 答案携带诸如 `[file:27#...]` 的引用；在当前工具结果限制下没有
  报告截断。

另一项手动检查演练了持久化队列。任务依次经过 `queued`、`parsing`、
`chunking`、带有 `Embedding x / y` 计数的 `embedding`、
`summarizing` 和 `ready`；文件在就绪之前不会出现在搜索中。在设置中
保存的已更改 worker 值会被下一轮 worker 循环读取，无需重启；更改的
分块目标只影响后续摄取。

集成测试套件仍然不依赖提供商，并且没有用这个语料进行扩展。

## 开发检查

```bash
# Everything at once (offline lint, then tests, then the contract gate)
make lint
make test
make api-check
make audit        # needs network

# Backend
cd backend
uv run ruff check .
uv run mypy app script
uv run lint-imports          # layer and slice-boundary contracts
PYTHONUTF8=1 uv run bandit -r app script -c pyproject.toml
uv run pip-audit
PYTHONUNBUFFERED=1 uv run pytest -q 2>&1 | tee /tmp/apsor-archive-pytest.log

# Frontend
cd frontend
bun run lint
bun run typecheck
bun run i18n:check
bun run check:boundaries     # workspace import boundaries
bun run test
bun run build
bun audit
```

`make lint` 是架构与安全闸门：ruff、mypy、让路由器、服务、领域代码和各切片
守在自身层级内的 import-linter 契约、bandit、ESLint、TypeScript、i18n 键值
一致性，以及前端工作区边界检查。分支遵循 Gitflow：`feat/*` 和 `fix/*` 从
`develop` 创建并通过 pull request 合并回去，`develop` 再合并到 `main` 进行发布。

集成测试套件在同一实例上使用一个真实的 PostgreSQL 测试数据库
（`apsor_archive_test`），顺序运行，并在测试之间重置每张被跟踪的表。
数据库由 `alembic upgrade head` 构建，而不是 `create_all`，因此
`apsor_app` 角色、授权和 RLS 策略在每个请求中都存在。每个测试都会演练
真实的 HTTP 接口和数据库。多用户测试覆盖
root/user 生命周期、强制更改密码、一次性临时密码、禁用/重置的会话
撤销、仅 root 的账户和全局设置、跨文件/文件夹/记忆/摘要/对话/
问题/提示词的私有档案隔离、每账户提示词上限、直接 SQL 的 RLS 拒绝、
`commit_and_reapply` 在检查点之后恢复作用域上下文、每轮用量核算和
格式错误补全的上限、账户用量汇总、模拟往返、root 密码重新认证，以及 root
密码轮换撤销模拟会话。Agent 测试覆盖运行时设置默认值、完整 PUT/
重置、校验、后续运行使用的运行时快照、自动和手动压缩、清空、边界
处的页面上下文重新附加、重试、并行/顺序工具执行、人工保存记忆审批
（批准前不写入、重启后存活、恰好一次批准、拒绝、孤立/已归档的失败
关闭恢复）、审批开关（默认等待路径、关闭时由后端直接授权写入，以及
待处理行在开关更改后存活）、已保存问题库、两个只读网页工具（包括
分页模式遍历和长行换行），以及压缩摘要 XML。提供商覆盖为每种能力
创建多个已保存行，证明部分唯一活动索引、清除密钥而从不返回明文、
测试注入的提供商探测，并验证删除后不会复用标识 id。提示词覆盖创建、
列出、更新、按 `sort_order` 排序、最多 20 行并删除常用提示词。
文件库测试还会在没有视觉提供商的情况下上传图像，并验证文件名说明
文字、已存储原始文件、路径列表和搜索结果；其 R2 用例使用假客户端
演练适配器，并在无网络访问的情况下检查缺失对象的转换。

最新的迁移是 `d6a1f3c8e2b7`。此分支上
`agent_config` 之后的迁移是：

- `f3c8d5a1b7e2` 删除轮次范围的工具结果预算；
- `a6e2f9c4d1b8` 把每个结果的工具字符上限提高到 100,000；
- `c9f1a2b3d4e5` 把 `max_total_tokens` 提高到 100,000，把
  `compaction_threshold_tokens` 提高到 75,000；
- `b7d2e9c4a1f6` 创建 `saved_question` 及其对话外键/索引；
- `e2b7c4d9a6f1` 把 `max_steps` 默认值从 8 提高到 24，并更新一行
  未被改动过的默认记录；
- `d1e2f3a4b5c6` 创建 `file_ingest_job`，包含其状态/来源/范围检查、
  活动路径唯一索引和文件外键；
- `d4b8e6f1a2c7` 创建单例 `ingest_config`，强制执行其范围和重叠
  规则，并预置第 `1` 行；
- `b3e5c7d9f1a2` 向 `agent_config` 添加 `context_window_tokens`，
  服务器默认值为 1,000,000，并带有 8,000–2,000,000 的检查约束；
- `c8f2a4b6d9e1` 向 `agent_config` 添加非空的
  `save_memory_requires_approval` 布尔值，服务器默认为 `true`；
  现有行会收到 `true`；
- `f2b3c4d5e6a7` 创建 `agent_approval`，包含其状态检查、对话/运行/
  条目外键、状态索引，以及待处理 `(run_id, tool_call_id)` 的部分
  唯一索引；
- `8f4b2c6d9e01` 删除已停用的 `media_ngram` 和 `media_asset` 表。
  其降级会重建原始媒体架构；
- `c4d8e2f6a1b9` 创建显式的 `folder` 表，从 `tree_node` 复制当前
  文件夹行及其 id，并删除 `tree_node`。文件叶现在派生自
  `file.raw_file_path`。降级会重建当前文件夹行和当前文件叶；
- `d5e9f3a7b2c1` 为 root 撰写的第一个系统区段创建单例
  `system_prompt` 表；
- `e1a2b3c4d5f6` 把 `ai_provider_config` 拆分为四张能力表
  （`chat_provider_config`、`embedding_provider_config`、
  `web_search_provider_config`、`web_fetch_provider_config`），
  复制现有聊天/嵌入行，并创建每张表的部分唯一活动索引；
- `a3f7c9d1e5b2` 创建 `frequently_used_prompt`，并预置过去硬编码在
  聊天空状态中的三个快捷方式；
- `b8d2e4f6a1c3` 在 Apsor Archive 更名后把 `dendro-hash-384` 分块
  重新标记为 `apsor-hash-384`；
- `c9e1f3a5b7d2` 用有序的 `system_prompt_section` 行替换单例
  `system_prompt` 表，并复制现有提示词作为第一个区段；
- `f4a1c7d9e2b3` 添加 `memory.title`（从内容回填）、`deprecated_at` /
  `deprecated_reason`、`system_prompt_section` 上用于可编辑内置覆盖的
  `builtin_key`，以及 `app_user.display_name` / `bio`。旧的“已弃用
  必须有后继者”检查变成“后继者或直接弃用时间戳”。降级会以
  `NOT VALID` 重新添加旧检查，因此直接弃用会保留其行；
- `b7e2d4f6a8c1` 创建带有有序标题/内容行的 `user_profile_card`，
  把现有的 `app_user.bio` 迁移到 `About` 卡片，并删除唯一的 bio 列；
- `e5c1a9d3b7f2` 把自定义区段和内置覆盖统一到一张
  `system_prompt_section` 表。升级会把有效的内置正文作为普通行
  生成在自定义行之后，删除覆盖行，并删除 `builtin_key` 及其约束。
  现在所有行都可以编辑、删除和重新排序；`reset` 会用四个预置默认值
  替换整个集合；
- `b8f4c2d9e6a1` 把 `max_tool_calls_per_turn` 默认值从 6 提高到 20，
  并提升一行未被改动过的已存储默认记录；
- `e8f1c4d2a7b9` 为每张私有表添加 `user_id` 归属、复合
  `(id, user_id)` 谱系外键、每账户唯一索引、`file.storage_backend` /
  `file_ingest_job.storage_backend`、单 root 部分唯一索引，以及
  `role` / `is_active` / `must_change_password` 账户列。它把现有行
  回填到最旧的账户，创建非登录 `apsor_app` 角色，撤销其对
  `alembic_version` 的权限，并在私有表上启用带有所有者策略的强制
  RLS，在全局配置表上启用读/root 写策略。认证表留在 RLS 之外；
- `f9c2a7d4e6b1` 向 `agent_run` 添加每次运行的令牌/API
  调用计数器，向 `app_user` 添加每账户汇总、用量增量触发器，以及
  可空的 `user_session.impersonator_user_id` 模拟标记。它从
  assistant 条目 JSON 回填历史用量，并且强制 RLS 回填需要
  superuser/BYPASSRLS 迁移角色；
- `a4c8e2f6b9d1` 删除 `max_total_tokens` 字段及其检查约束，修复未低于
  上下文窗口的压缩阈值，并用
  `compaction_threshold_tokens < context_window_tokens` 取代旧阈值规则。
  降级会恢复 100,000 令牌上限，并在存储阈值需要时提高该上限；
- `a1c3e5f7b9d2` 把压缩阈值范围提高到 1,000,000 令牌。降级会先把存储值夹回
  200,000，再恢复旧检查约束；
- `c2f6a8d4e1b3` 把
  `ingest_config.vision_description_language` 添加为非空 `varchar(80)`，
  服务器默认值为 `English`，并带有去除首尾空白后的长度检查。降级会删除
  检查约束和列；
- `f7a3c2d9e1b4` 新增可为空的
  `ingest_config.vision_image_prompt` / `vision_document_prompt` 模板、
  `file` 提示词指纹列，以及 `file_ingest_job.source_file_id` 与其
  拥有者安全的复合外键、重新摄取检查、活动来源唯一索引和查询索引。
  它不会预置或回填提示词／指纹值。降级会先删除重新摄取任务，再恢复旧的
  来源类型检查；
- `a4c9e2f7b1d6`新增八个 `app_user` 分配列及两个指向
  `chat_provider_config` 的 `ON DELETE SET NULL` 外键、七项检查约束、
  `chat_provider_config.max_output_tokens`（256–131,072）、允许 `anthropic`
  的更宽聊天提供商检查，以及四个新的 `agent_config` 列
  （`compaction_prompt`、`compaction_max_output_tokens`、
  `model_escalation_enabled`、`agent_max_output_tokens`）。它会把优先级
  最低的活动非 `none` 聊天行及其模型回填到尚未分配的账户；如果没有这样的
  行，每个账户都会保持未分配。升级后创建的新账户也会继承同一个主要端点
  与模型；只有在没有活动聊天行时才会保持未分配。`app_user` 仍在 RLS 之外，因此不需要更改
  策略或授权。降级会删除分配列，并在仍有 `anthropic` 行时拒绝恢复较窄的
  提供商检查；
- `d8f2a6c4e1b9` 移除 `agent_config.max_steps` 和
  `agent_config.max_tool_calls_per_turn` 及其检查约束，以及
  `parallel_within_tool_calls` 关系，因此工具密集的轮次会一直运行到模型回答
  为止。并发上限 `max_parallel_tools` 保留。降级会恢复两个列，并把恢复的调用
  上限提高到至少 `max_parallel_tools`；
- `c3e7a1f5b9d2` 放宽 `file`、`file_ingest_job` 和 `agent_chat_attachment`
  上的 `storage_backend` 检查，允许 `s3`（RustFS、AWS S3、MinIO）；`rustfs`
  只是配置别名，`r2` 仍是独立的值。降级会恢复只有两个值的检查，并在仍有行
  记录 `s3` 时失败；
- `c7a3e9f1d5b2` 创建私有的 `file_thumbnail` 表：每个文件版本
  一张极小的 WebP（最多 32 KiB、512 px）、指向 `file` 且带
  `ON DELETE CASCADE` 的所有者安全复合外键、带所有者策略的强制 RLS，以及
  `apsor_app` 授权。现有文件由 worker 回填补上。降级会删除该表；
- `a7d3c9e1f5b2` 创建私有的 `companion`、`companion_frame` 和
  `companion_preference` 表，每张都带 `user_id`、仅限所有者的强制 RLS 和
  `apsor_app` 授权。帧通过所有者安全的复合外键引用其伙伴并一起级联删除；
  偏好行以 `user_id` 为键。降级会删除这三张表；
- `b8e4d2f6a1c3` 创建私有的 `companion_story`、
  `companion_lore_fragment` 和 `companion_bond` 表，带仅限所有者的强制 RLS 和
  `apsor_app` 授权：账户按语言保存的伙伴人设与传说副本、其片段，以及解锁传说
  层级的完成对话数。自定义伙伴的故事会随伙伴一起级联删除。降级会删除这三张表。
- `c5f1a8d3e7b4` 为 `companion_preference` 新增 `size`（`compact`、
  `medium`、`full`，默认 `full`）与 `opacity_mode`（`opaque`、`translucent`、
  `auto`，默认 `opaque`），附检查约束与服务器默认值。RLS 与授权不变；降级会删除
  这两个字段。
- `d2b6f4a8c1e9`为 `companion_preference` 新增可为 NULL 的
  `scale` 浮点数（0 为精简、1 为完整），用于直接在屏幕上缩放，附范围检查。
  NULL 表示“使用 `size`”；只发送 `scale` 时会推导出 `size`，只发送 `size` 时会清除
  `scale`。RLS 与授权不变；降级会删除这个字段。
- `e4c8a2f6b0d3` 新增 `companion_lore_told`（每个账号、伙伴与片段的
  `told_count`、`offered_at`、`last_told_at`、`source`）与
  `companion_bond.last_story_run`，用于故事时刻的节奏。仅限所有者的 RLS。
- `f1a6c3e8b2d4` 新增全局、可由 root 编辑的伙伴世界表（预设角色、片段、
  设定词条、世界观文档与修订、配置、提示词模板、种子状态），从 `lore/`
  预置，并通过 `seed_hash`／`admin_modified`／`upstream_seed_hash`
  保留 root 的修改。所有人可读、仅 root 可写。
- `a2d7e4f9c3b5` 新增 `app.admin_scope = 'companion'` 策略（root 只能读写
  伙伴故事相关的数据行，永远接触不到档案馆内容）、由管理员管理的账号表
  （账号可读不可写）、新的羁绊字段、`companion_lore_fragment.refs`，以及只能
  追加的 `companion_admin_access_log`。
- `b3e8f5a1d6c7` 新增 `companion_generated_story` 与 `companion_story_job`，
  供 worker 撰写生活故事。
- `e7b2d5a9c4f1` 新增 `chunk.embedding_failures` 与待嵌入的部分
  索引，并把 JSON `null` 嵌入转为 SQL NULL，让 worker 能在供应商或额度中断后
  补上向量。
- `d6a1f3c8e2b7`（当前 head）把所有传说表的层级换成分量（`first` →
  `everyday`、`familiar` → `past`、`rare` → `heart`），移除解锁计数与解锁时间，
  新增 `companion_bond.first_met_at`，让 `companion_lore_told.source` 可记录
  `recall`，并按对话冻结的伙伴，给每条过去的助手回复盖上
  `data.speaker = {ref, name}`。

更早的时候，`e7a1c4b9d2f6` 创建了单例 `agent_config` 表并预置了
第 `1` 行。集成测试套件在一次性 PostgreSQL 数据库上运行迁移链，
因此会验证角色、授权和 RLS 策略；Alembic 降级仍会单独针对开发
数据库进行验证。

## 项目结构

Python 包是 `apsor-archive-backend`（CLI `apsor-archive`），客户端
包是 `apsor-archive-frontend`。

```text
backend/
  app/
    main.py                     API assembly, lifespan, gzip, SPA mount
    worker.py                   dedicated durable-ingestion process
    bootstrap.py                shared process setup and background loops
    shared/                     error registry and list envelope
    infrastructure/             config, database, cache, embeddings, AI, web, files
    module/knowledge/
      domain/                   chunking, n-grams, BM25 terms, timeline, summary
      model/                    SQLAlchemy models incl. ingest jobs/config
      repository/               persistence, retrieval, and job-queue queries
      service/                  orchestration, indexing, ingest jobs/settings
      router/                   HTTP adapters incl. file intake and settings
      schema/                   Pydantic contracts
      exception/                stable error codes
    module/auth/                accounts, roles, sessions, profile cards
    module/agent/               transcript, runtime settings, compaction, tools,
                                saved questions, SSE
    module/prompt/              editable frequently used chat prompts
    module/web_research/        web search/fetch service, URL safety, cache
  alembic/                      migrations
  tests/                        integration tests (PostgreSQL, offline fakes)
frontend/
  src/app/
    component/                  shared archive UI
    generated-apis-types/       committed Orval client
    auth/                       setup/login gate, forced password change
    accounts/                   root-only account directory
    agent/                      page capture, trace, and inspector panels
    chat/                       reading room, retry, context actions
    questions/                  saved-question Q&A library
    settings/                   role-filtered provider and runtime panels
    library/                    files, media gallery, memories, preview modal, intake
    dashboard/ search/ timeline/ about/ ...
  src/apis/fetch-client.ts      the only JSON mutator
  src/apis/agent-stream.ts      SSE transport for agent turns
  src/lib/                      formatting and safe highlighting
  src/styles/                   paper / night archive tokens
  scripts/                      PDF.js asset copy, i18n parity, workspace boundaries
  dist/                         generated build output, gitignored
docker-compose.yml              production stack: Caddy + Cloudflare Tunnel
docker-compose.dev.yml          local dependencies
docs/cloudflare-tunnel.md       tunnel deployment, backup, and security guide
docker/caddy/                   non-root reverse proxy
```
