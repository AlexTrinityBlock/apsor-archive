<div align="center">
  <img src="frontend/public/icon-512.png" alt="Apsor Archive" width="112" height="112">
</div>

<h1 align="center">Apsor Archive</h1>

<p align="center">
  面向家庭或小型团队的本地优先、私密知识与记忆档案。
</p>

<p align="center">
  <a href="https://github.com/AlexTrinityBlock/apsor-archive"><img src="https://img.shields.io/badge/version-0.1.0-171717" alt="Version 0.1.0"></a>
  <a href="LICENSE"><img src="https://img.shields.io/github/license/AlexTrinityBlock/apsor-archive?label=license&amp;color=171717" alt="License: MIT"></a>
  <img src="https://img.shields.io/badge/self--hosted-yes-171717" alt="Self-hosted">
  <a href="https://github.com/AlexTrinityBlock/apsor-archive/pulls"><img src="https://img.shields.io/badge/PRs-welcome-171717" alt="Pull requests welcome"></a>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.13-3776AB?logo=python&amp;logoColor=white" alt="Python 3.13">
  <img src="https://img.shields.io/badge/react-19-61DAFB?logo=react&amp;logoColor=black" alt="React 19">
  <img src="https://img.shields.io/badge/vite-8-646CFF?logo=vite&amp;logoColor=white" alt="Vite 8">
  <img src="https://img.shields.io/badge/bun-1.3.6-fbf0df?logo=bun&amp;logoColor=black" alt="Bun 1.3.6">
  <img src="https://img.shields.io/badge/postgresql-17-4169E1?logo=postgresql&amp;logoColor=white" alt="PostgreSQL 17">
  <img src="https://img.shields.io/badge/docker%20compose-2496ED?logo=docker&amp;logoColor=white" alt="Docker Compose">
</p>

[English](README.md) · [繁體中文](README.zh-TW.md) · **简体中文**

## 目录

- [亮点](#亮点)
- [技术栈](#技术栈)
- [快速开始](#快速开始)
  - [Docker Compose（常规）](#docker-compose常规)
  - [对象存储（RustFS、R2、S3 或本地）](#对象存储rustfsr2s3-或本地)
  - [在应用中配置提供商](#在应用中配置提供商)
  - [每个账户的模型分配](#每个账户的模型分配)
  - [网页研究工具](#网页研究工具)
  - [常用提示词](#常用提示词)
  - [聊天伙伴](#聊天伙伴)
  - [Agent 运行时设置](#agent-运行时设置)
  - [摄取运行时](#摄取运行时)
  - [本地开发](#本地开发)
  - [Cloudflare Tunnel](#cloudflare-tunnel)
- [工具接口](#工具接口)
  - [文件夹工作区](#文件夹工作区)
  - [Agent 对话](#agent-对话)
  - [已保存的问题](#已保存的问题)
  - [聊天阅读室](#聊天阅读室)
  - [聊天工作区](#聊天工作区)
  - [资源预览](#资源预览)
  - [账户、角色与会话](#账户角色与会话)
  - [生成的 API 客户端与漂移](#生成的-api-客户端与漂移)
  - [载入真实语料](#载入真实语料)
  - [长文档验证](#长文档验证)
- [检索如何工作](#检索如何工作)
  - [我需要嵌入模型密钥吗？](#我需要嵌入模型密钥吗)
  - [什么是带符号哈希嵌入器？](#什么是带符号哈希嵌入器)
- [数据模型](#数据模型)
- [开发检查](#开发检查)
- [项目结构](#项目结构)
- [安全与隐私](#安全与隐私)
- [许可证](#许可证)

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

## 快速开始

### Docker Compose（生产环境）

生产栈是 **Cloudflare Tunnel → Caddy → API + 摄取 worker**，并在私有的 Compose
网络上运行 PostgreSQL、Valkey、RabbitMQ，以及（默认）随附的 RustFS 对象存储。
它不发布任何主机端口。

请运行设置向导，而不是手动编写环境变量：

```bash
./start.sh setup        # or: make setup
mkdir -p data && sudo chown -R 10001:10001 data
docker compose up -d --build
```

向导会询问公开主机名、存储后端（默认为随附的 **RustFS**，也可选 Cloudflare R2、
任何 S3 兼容端点或本地磁盘）、会话时长、可选的 DeepSeek 密钥，以及 Cloudflare
Tunnel 令牌。它会写出非机密的 `.env`，生成 RustFS 与 RabbitMQ 凭据，把粘贴的
密钥存入 `.secrets/*.env` 与 `secrets/*.txt` 且不回显，除非你确认覆盖，否则保留
任何现有文件，并打印容器读取机密文件所需的 `sudo chgrp` 命令。
`./setup.sh --defaults` 以非交互方式运行同一流程（生产环境搭配 RustFS）；加上
`--dev` 则写出开发用的 `.env`。

把 Cloudflare Tunnel 的公开主机指向 **HTTP `caddy:80`**，然后打开
`https://$APSOR_PUBLIC_HOST`。请把 `APSOR_PUBLIC_HOST` 放进 `.env`，重启后
才能保留主机匹配设置。首次访问会要求创建 root 账户。root 随后可以从
**账户** 创建普通账户；每个新账户会收到一次性临时密码，并必须在首次登录时
更改。新账户还会继承部署的主要聊天端点与模型，因此聊天和后台 AI 可立即
使用；如果部署没有活动的聊天端点，账户会保持未分配，root 必须先分配。
PostgreSQL 使用命名卷；本地原始字节和生成的密钥文件位于宿主机的 `./data`
目录下。原始文件字节会写入向导所选的后端；请见
[对象存储](#对象存储rustfsr2s3-或本地)。

> 注意：`./data` 会以绑定挂载方式挂入容器，容器进程以 uid `10001`
> 运行。请在首次启动前创建该目录并修正其所有者，否则上传和
> 原始字节写入会失败。如果宿主用户已经是 uid `10001`，可以跳过
> `sudo chown`。

`postgres-data` 卷被固定为显式的物理名称：
`docker-compose.yml` 使用 `apsor-archive_postgres-data`，
`docker-compose.dev.yml` 使用 `apsor-archive-dev_postgres-data`，
因此 Compose 项目重命名不会让数据库成为孤儿。在此次重命名之前
创建的栈使用了不同的物理卷名，因此启动前请把那个卷的内容复制到
新卷（或在本地 Compose 文件中保留旧名称）。否则 PostgreSQL 会
初始化一个空数据库。

Docker 构建会在前端阶段从 `frontend/` 编译前端，因此修改前端代码后
直接运行 `docker compose up --build` 即可，不需要手动构建。只有想在本机
预览时才需要运行 `cd frontend && bun run build`。

要启用 AI 回答和 AI 摘要：

```bash
mkdir -p .secrets
printf 'APSOR_DEEPSEEK_API_KEY=sk-your-key\n' > .secrets/deepseek.env
chmod 755 .secrets
sudo chgrp 10001 .secrets/deepseek.env
chmod 640 .secrets/deepseek.env
docker compose up -d --build
```

Compose 文件以只读方式挂载 `.secrets/`。应用自己读取该 env 文件，
因此密钥永远不会成为容器环境变量，也不会出现在
`docker compose config` 中。API 容器以 uid `10001` 运行，因此该文件必须能被
这个 uid 读取：组 `10001` 搭配权限 `640`，或在单用户主机上使用 `644`。密钥被
gitignore，API 也从不返回它。
没有密钥时，摘要会回退到确定性的抽取式形式，图像上传使用
文件名说明文字，Agent 消息返回 `503 agent_not_configured`。

### 对象存储（RustFS、R2、S3 或本地）

`APSOR_STORAGE_BACKEND` 为新原始字节选择默认后端。设置向导会设置它；除了
`local` 之外，所有选项都使用同一个 S3 兼容适配器。

| 值 | 字节写入位置 | 凭据 |
|---|---|---|
| `rustfs` | 随附的 RustFS 服务（以 `COMPOSE_PROFILES=rustfs` 启动）。新安装的默认值。 | 由向导生成到 `.secrets/s3.env` 与 `secrets/rustfs_*_key.txt` |
| `r2` | 私有的 Cloudflare R2 存储桶 | `.secrets/r2.env` |
| `s3` | 任何 S3 兼容端点（AWS S3、MinIO、另一个 RustFS） | `.secrets/s3.env` |
| `local` | `APSOR_DATA_DIR`；开发和测试的默认值 | 无 |
| `auto` | `.secrets/r2.env` 完整时用 R2，否则用 S3，再否则用本地 | — |

`rustfs` 是 `s3` 的别名。未设置 `APSOR_STORAGE_BACKEND` 时，生产 Compose 文件会
使用 `auto`，因此现有的 R2 部署无需修改 `.env` 就会继续写入 R2。每一行都会记录
保存其字节的后端（`local`、`r2` 或 `s3`），而设置完整的每个后端都保持可读，
因此分阶段迁移可以提供混合档案。

非机密设置放在 `.env`：

- R2：`APSOR_R2_ENDPOINT_URL`（`https://<account-id>.r2.cloudflarestorage.com`，
  没有默认值）、`APSOR_R2_BUCKET`（`apsor-archive`）、`APSOR_R2_REGION`
  （`auto`）、`APSOR_R2_PREFIX`。
- S3／RustFS：`APSOR_S3_ENDPOINT_URL`（Compose 默认 `http://rustfs:9000`）、
  `APSOR_S3_BUCKET`（`apsor-archive`）、`APSOR_S3_REGION`（`us-east-1`）、
  `APSOR_S3_PREFIX`、`APSOR_S3_ADDRESSING_STYLE`（`path` 或 `virtual`），以及
  `APSOR_S3_CREATE_BUCKET`（首次写入时创建缺失的存储桶；随附的 RustFS 需要它）。

访问密钥绝不放进 `.env` 或容器环境变量。Compose 以只读方式挂载 `.secrets/`，
由应用自己读取 `r2.env`／`s3.env`；RustFS 容器则以 Docker secrets 读取自己的
密钥对。它们都以 uid `10001` 运行，因此这些文件需要组 `10001` 与权限 `640`
（向导会打印 `sudo chgrp` 命令）。存储桶保持私有：没有预签名 URL，没有公开
访问，也不对 `files/` 设置生命周期过期。`data/.secret_key` 是 Fernet 主密钥，
始终留在本地；请与 PostgreSQL 分开备份。请把 `apsor-archive_rustfs-data` 卷
（或外部存储桶）与数据库一起备份为同一组备份。

要把现有档案从本地磁盘迁移到 R2，请停止 API 和 worker，并在
`backend/` 下运行存储 CLI：

```bash
uv run python -m script.migrate_storage_to_r2 --dry-run
uv run python -m script.migrate_storage_to_r2 --copy
uv run python -m script.migrate_storage_to_r2 --verify
# only after a verified backup and rollback window
uv run python -m script.migrate_storage_to_r2 --delete-local
```

`--copy` 会先上传并校验大小和 SHA-256，然后把匹配的 `file` 行和
可重试的 `file_ingest_job` 行标记为 `storage_backend='r2'`。请把
PostgreSQL 转储、数据目录备份和 R2 存储桶内容作为一个备份集一起
保存。使用版本控制或对象同步任务备份存储桶；软删除的文件会保留
其对象。

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
[`backend/app/module/companion/lore/BIBLE.md`](backend/app/module/companion/lore/BIBLE.md)，
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
使用该对话的语言），以及传说，也就是它自己的记忆。没有任何记忆被上锁：每段记忆
都带有分量（日常小事、往事、心底的事），要不要说、何时说、说多少，由图书馆员
自己决定，她也知道你们已经相识多久。相关的记忆可能以独立区块附在消息或工具结果
旁，她也能用 `recall_my_memories` 工具自己回想，包括她与其他图书馆员过去对这个人
说过的话（每条过去的回复都记得是谁说的）。她的记忆永远不是档案证据，也不会被
引用；`search_knowledge` 只搜索这个人的档案馆。每个账户都可以按语言编辑任何
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

### Cloudflare Tunnel

生产 Compose 栈已包含 `cloudflared`、Caddy 和 API。请在 Cloudflare
仪表板添加一个公开主机：

- **Service type**：`HTTP`
- **URL**：`caddy:80`

`cloudflared` 主动向外连接，因此不需要路由器端口转发。Caddy 只服务
`APSOR_PUBLIC_HOST` 指定的主机，并对其他所有主机返回 `404`；不要把第二个
公网主机名加入 tunnel 入口。令牌权限见 `secrets/README.md`，完整的英文
部署、备份、安全与疑难解答指南见
[`docs/cloudflare-tunnel.md`](docs/cloudflare-tunnel.md)。

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
  覆写的伙伴人设与传说、其片段，以及完成的运行与对话次数，和初次相遇的时间。
- `ingest_config`：一行（`id=1`），带有经过校验的 worker 轮询、
  提取、在途、嵌入和分块大小设置。它不是分块来源；队列引用最终
  发布的文件。

原始字节不存储在 PostgreSQL 中。它们位于本地磁盘、私有 R2 存储桶，或
S3 兼容存储桶（默认为 RustFS）中，由每个文件的 `storage_backend` 选择；提取的分块及其 n-gram
保留在 PostgreSQL 中。

代码、注释和文档以英语编写，英语为规范版本。界面和本 README 也提供完整的
繁体中文与简体中文翻译，并与英文源一起更新。

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

## 安全与隐私

- 在暴露服务之前完成首次运行设置。在没有任何账户时，
  `/api/v1/auth/setup` 按设计是公开的；在创建 root 账户之前，不要
  让全新实例可通过 tunnel 访问。
- 一个 root 加上普通账户保护档案。密码使用 Argon2 哈希；会话令牌在
  `user_session` 中只存储为 SHA-256 哈希。cookie 是 HttpOnly、
  SameSite=Lax，并在 `APSOR_COOKIE_SECURE=true` 时启用 Secure。
  临时密码只返回一次，从不记录或缓存，账户必须在加载内容之前更改它。
- 每条私有行都携带 `user_id`；复合外键把谱系限制在一个账户内，
  `apsor_app` 上的 PostgreSQL 强制行级安全会拒绝跨账户读写，即使
  缺少服务过滤条件。仅 root 的路由守卫保护账户和全局设置，但 root
  不是数据超级用户，无法通过普通 API 查询读取另一个账户的档案。
  root 密码重置和显式模拟是刻意的受信任恢复能力，可以把登录访问权
  转移给目标账户；停止模拟需要 root 密码、删除该会话并签发新的 root
  会话。请把 root 视为最高信任凭据，不要把 RLS 当作针对恶意 root
  的保护。
- **RLS 是应用边界，而不是主机边界。** 部署登录是用于迁移和维护的
  PostgreSQL 超级用户；应用会为请求事务切换到 `apsor_app`。任何
  本地操作系统用户、数据库/缓存网络上的任何容器，或任何能读取
  `.secrets/`/`.env` 的人，都可以绕过 API 和 RLS。请保持主机可信，
  把数据库和缓存绑定到 localhost 或内部网络，使用不同的主机账户，
  为任何共享主机设置强数据库/缓存密码，并在暴露后轮换凭据。未来的
  加固步骤是专用的非超级用户运行时登录加上单独的维护凭据。
- 生产 Compose 文件不发布任何主机端口；Cloudflare Tunnel 连接到 Caddy，
  Caddy 再连接到 API。登录限流在内存中，因此是单进程的；请运行一个
  API 进程，或在横向扩展前把限流迁移到 Valkey。
- 路径会拒绝遍历段、反斜杠、控制字符和过长的值。上传限制为 10 MB，
  并受扩展名允许列表限制。
- 来自文件和记忆的 HTML 通过 React 作为文本渲染。Agent Markdown
  使用 `skipHtml`；DOCX 预览在禁用脚本的沙箱中运行，PPTX 幻灯片则绘制到本地
canvas。UI 从不使用
  `dangerouslySetInnerHTML`。
- DeepSeek 密钥位于 `.secrets/deepseek.env` 或环境中。它永远不会被
  记录、返回或提交。从设置页面保存的密钥在 PostgreSQL 中加密，并且
  只作为四字符提示返回。
- 对象存储凭据位于被 gitignore 的 `.secrets/r2.env` 或 `.secrets/s3.env`
  （随附的 RustFS 另有 `secrets/` 下的 Docker secret 文件），以只读方式挂载，
  永远不会成为容器环境变量。存储桶是私有的，没有预签名或公开 URL。
- 摘要和 agent 轮次会发生 AI 调用。如果提供商失败，API 会返回稳定
  的错误，而不是编造答案。

## 许可证

MIT。见 `LICENSE`。
