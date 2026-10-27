<div align="center">
  <img src="frontend/public/favicon.svg" alt="Apsor Archive" width="112" height="112">
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
  - [对象存储（本地或 R2）](#对象存储本地或-r2)
  - [在应用中配置提供商](#在应用中配置提供商)
  - [网页研究工具](#网页研究工具)
  - [常用提示词](#常用提示词)
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
> 问题问答库、持久化异步摄取、专用的 PDF/DOCX/图像/文本预览引擎、
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
- **Agent 的限制由数据库支撑。** 模型上下文窗口、轮次预算、
  压缩阈值、步骤与工具上限、并行宽度和结果预算都存放在一行经过校验的
  `agent_config` 记录中，无需重启即可应用于新的运行。上下文窗口是模型
  元数据，不是轮次预算。
- **长线程可以被折叠或清空。** 压缩会写入一个摘要边界；清空会启动
  一个空的活动上下文。两种情况下，完整的对话记录仍然可读。
- **记忆是线性的、可追溯的。** 新的判断可以取代旧的判断。
  旧记忆会离开检索界面，但仍可通过其链条读取。
- **搜索是混合式的。** 基于 CJK 二元组和拉丁词元的 BM25 与向量
  召回并行运行。结果会去重并融合，同时记录原因。
- **时间采样是诚实的。** 时间线为每种事件类型最多返回五个锚点，
  并准确报告跳过了多少事件。
- **AI 回答有据可依。** DeepSeek 收到的是检索到的段落，而不是整个
  文件库；每条论断都必须带引用。没有密钥时，Agent 轮次会失败关闭。
- **问题比对话更长久。** 可以在还没有答案时保存问题，稍后再提问，
  并把答案、引用、运行状态以及指向对话的链接保留在同一行。编辑问题
  会清除过期的答案，而不是在屏幕上留下一对不匹配的内容。
- **图像保存在文件库中。** 图像是一条普通的文件记录，带有原始字节、
  路径和分块。支持视觉的聊天提供商会补充 OCR 和说明文字元数据；
  没有这样的提供商时，由文件名派生的说明文字可让本地上传仍可搜索。
  不存在单独的图像索引。
- **文档自行选择提取器。** PDF 先尝试文本，扫描页则回退到视觉。
  DOCX、TXT、JSON、CSV 和日志使用文本，并辅以 AI 结构化元数据；
  图像使用视觉或文件名回退。
- **界面支持三种语言。** 可以在设置页面切换英语、繁体中文和简体中文。
  选择按浏览器存储，应用于整个界面，但从不应用于档案内容。
- **档案是私密的、多账户的、本地优先的。** 一个 root 账户管理账户和
  全局运行时设置；其他每个账户都获得一个私有档案，包含文件、文件夹、
  分块、记忆、摘要、对话、条目、运行、审批、已保存的问题、提示词和
  个人资料卡。PostgreSQL 行级安全在每张私有表上强制归属，因此即使
  缺少查询过滤条件，也无法暴露他人的档案。密码使用 Argon2，会话使用
  HttpOnly cookie。请在自己的机器上运行；只有在具备自己的访问控制时，
  才把它放到 Cloudflare Tunnel 之后。
- **原始字节可以存放在 Cloudflare R2 中。** `APSOR_STORAGE_BACKEND=local|r2`
  选择新原始文件的写入位置。读取时遵循每一行记录的存储后端，因此
  分阶段迁移可以提供混合档案。R2 存储桶是私有的，应用从不签发
  预签名 URL 或公开 URL。

## 技术栈

| 层 | 选择 |
|---|---|
| API | Python 3.13、FastAPI、SQLAlchemy 2 async、Alembic、psycopg 3 |
| 存储 | PostgreSQL 17（`pg_trgm` 用于路径模糊搜索）；原始字节位于本地磁盘或私有 Cloudflare R2 |
| 缓存 | Valkey / Redis 兼容，带内存回退 |
| 检索 | CJK 二元组 + 拉丁词元 n-gram、BM25、带符号哈希向量、RRF |
| AI | DeepSeek `deepseek-flash`（OpenAI 兼容的聊天补全） |
| 前端 | React 19、TypeScript、Vite、React Router、React Query、Orval |
| 部署 | Docker Compose、可选的 Cloudflare Tunnel，或使用 `uv` 的裸机 |

## 快速开始

### Docker Compose（常规）

```bash
mkdir -p data
sudo chown -R 10001:10001 data
# The production Compose default is R2; local disk is the simplest first run.
APSOR_STORAGE_BACKEND=local docker compose up --build
```

> 注意：`./data` 会以绑定挂载方式挂入容器，容器进程以 uid `10001`
> 运行。请在首次启动前创建该目录并修正其所有者，否则上传和
> 原始字节写入会失败。如果宿主用户已经是 uid `10001`，可以跳过
> `sudo chown`。

打开 <http://127.0.0.1:8000>。首次访问会要求创建 root 账户。
root 随后可以从 **账户** 创建普通账户；每个新账户会收到一次性
临时密码，并必须在首次登录时更改。PostgreSQL 使用命名卷；
本地原始字节和生成的密钥文件位于宿主机的 `./data` 目录下。
生产 Compose 文件默认使用 `APSOR_STORAGE_BACKEND=r2`；其所需凭据见
[对象存储](#对象存储本地或-r2)，或者为自包含主机保留本地存储。

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
`docker compose config` 中。由于 API 容器以非 root 用户运行，
必须使用 `644` 权限。密钥被 gitignore，API 也从不返回它。
没有密钥时，摘要会回退到确定性的抽取式形式，图像上传使用
文件名说明文字，Agent 消息返回 `503 agent_not_configured`。

### 对象存储（本地或 R2）

`APSOR_STORAGE_BACKEND` 为新原始字节选择默认后端：

- `local` 写入 `APSOR_DATA_DIR` 下，是开发和测试的默认值。
- `r2` 写入私有的 Cloudflare R2 存储桶。两个生产 Compose 文件都
  默认使用 `r2`；首次启动或回滚时请设置 `APSOR_STORAGE_BACKEND=local`。

非机密的 R2 值是 `APSOR_R2_ENDPOINT_URL`、`APSOR_R2_BUCKET`
（部署中为 `apsor-archive`）、`APSOR_R2_REGION`（`auto`）和
`APSOR_R2_PREFIX`。账户端点没有默认值：在使用 `r2` 后端运行之前，
把 `APSOR_R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com`
放入 Compose 文件旁被 gitignore 的 `.env` 文件，或将其导出。
凭据位于被 gitignore 的 `.secrets/r2.env`，Compose 以只读方式
挂载它，应用自己读取，因此它们永远不会成为容器环境变量：

```bash
mkdir -p .secrets
# Fill these in locally; never commit the file.
printf 'APSOR_R2_ACCESS_KEY_ID=...\nAPSOR_R2_SECRET_ACCESS_KEY=...\n' \
  > .secrets/r2.env
chmod 755 .secrets
# Container uid 10001 needs read access; other host users do not.
sudo chgrp 10001 .secrets/r2.env
chmod 640 .secrets/r2.env
```

该文件必须可被容器 uid `10001` 读取（权限 `640`、组 `10001`，
或在单用户主机上使用 `644`）。存储桶保持私有：没有预签名 URL，
没有公开存储桶访问，也不对 `files/` 设置生命周期过期。
`data/.secret_key` 是 Fernet 主密钥，始终留在本地；请与 PostgreSQL
分开备份。

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

设置页面是配置提供商的常规方式，只有 root 账户可以编辑全局注册表。
它会写入四张独立的能力表，因此一种能力永远不会覆盖另一种：

- **聊天** — `chat_provider_config`：DeepSeek 或任何 OpenAI 兼容的聊天
  端点。允许保存多行；恰好有一行处于活动状态。
- **嵌入** — `embedding_provider_config`：离线 `hashing`、`openai` 或
  `openai-compatible`。允许保存多行；恰好有一行处于活动状态。
- **网页搜索** — `web_search_provider_config`：目前是 Tavily，并为未来
  的搜索 API 预留提供商适配器接缝。允许保存多行；恰好有一行处于
  活动状态。
- **网页抓取** — `web_fetch_provider_config`：目前是 Tavily `extract`。
  网页搜索和网页抓取刻意分成不同的行，因此它们可以使用不同的
  提供商或不同的凭据。

每张表都在 `is_active` 上有一个部分唯一索引；PostgreSQL 强制每种
能力最多只有一行活动记录。删除一行不会复用其标识 id。提供商行是
全局部署配置：只有 root 账户可以列出、编辑、测试或删除它们，
普通用户永远不会收到提供商密钥或全局运行时设置。API 从不返回
明文密钥：浏览器只会收到诸如 `...14f8` 的提示。`APSOR_SECRET_KEY`
提供 Fernet 主密钥。如果未设置，会在 `data/.secret_key`
（Docker 中为 `/data/.secret_key`）创建一个 `0600` 密钥文件，
因此加密值在重启后仍然有效。`APSOR_TAVILY_API_KEY` 是两种网页能力
的可选环境回退。

优先级是：**活动数据库行 → 环境 → 内置默认值**。设置页面会为每个
提供商标注其来源。更改嵌入模型不会重写现有向量；`reindex_required`
会发出警告。运行 **重新嵌入文件库**（或
`POST /api/v1/settings/providers/embedding/reindex`）以刷新当前分块。
向量搜索会跳过维度与当前嵌入器不匹配的分块。

提供商注册表 API：

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/settings/providers` | 四个能力组、掩码提示、活动行、重建索引建议 |
| `POST` | `/api/v1/settings/providers/{capability}` | 创建一个已保存的提供商；可选择将其激活 |
| `PUT` | `/api/v1/settings/providers/{capability}/{provider_id}` | 替换一个已保存的提供商 |
| `DELETE` | `/api/v1/settings/providers/{capability}/{provider_id}` | 删除一个已保存的提供商 |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/activate` | 使其成为该能力唯一的活动行 |
| `POST` | `/api/v1/settings/providers/{capability}/deactivate` | 清除活动行并回退到环境/默认值 |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/test` | 一次小型提供商请求及延迟 |
| `POST` | `/api/v1/settings/providers/embedding/reindex` | 使用活动提供商重新嵌入每个当前分块 |

`{capability}` 是 `chat`、`embedding`、`web_search` 或 `web_fetch`
之一。注册表响应在 `providers` 缓存作用域下缓存 30 秒；每次写入
提供商都会递增该作用域的版本。

### 网页研究工具

Agent 有两个用于外部研究的只读工具：

| 工具 | 作用 |
|---|---|
| `web_search` | 使用活动的 `web_search` 提供商搜索公共网络；返回标题、URL、分数和有界摘录。 |
| `web_fetch` | 使用活动的 `web_fetch` 提供商抓取一个公共 `http(s)` URL，并返回一个由服务器定义的 Markdown 页面。 |

Tavily 是第一个适配器（`/search` 和 `/extract`）。提供商接缝是一个
协议，因此可以在不更改工具层的情况下加入另一个搜索或抓取 API。
搜索结果在 `providers` 缓存作用域下缓存 15 分钟；写入提供商会使其
失效。`web_fetch` 会拒绝非 HTTP(S)、URL 中的凭据、
`localhost`/`.local`/`.internal`，以及私有或特殊用途的 IP 字面量。

`web_fetch` 会为每个 URL 缓存完整的提取文档一小时，因此翻页永远
不会再次调用提供商。它面向模型的参数只有 `url` 和 `page`
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

### Agent 运行时设置

`/settings` 上的 **Agent 运行时** 面板（仅 root）编辑单例
`agent_config` 行（`id=1`）。提供商和模型选择仍留在上方的 AI 设置中，
因此哪个模型作答仍然只有一个事实来源。全部十三个运行时值都存储在
PostgreSQL 中，无需重启即可应用于新的运行，并由每个账户共享。

| 方法 | 路径 | 用途 |
|---|---|---|
| `GET` | `/api/v1/agent/settings` | 有效配置、默认值、来源、`updated_at` |
| `PUT` | `/api/v1/agent/settings` | 完整替换；全部十三个字段都是必填 |
| `POST` | `/api/v1/agent/settings/reset` | 持久化并返回内置默认值 |

生成的操作是 `getAgentSettings`、`updateAgentSettings` 和
`resetAgentSettings`。

读取形状是 `{config, defaults, source, updated_at}`，其中 `source`
对于已存储的行是 `database`，当 API 不得不从默认值创建或修复该行时
是 `default`。`PUT` 要求完整快照：省略字段和多余字段都会被拒绝。

| 字段 | 默认值 | 范围 |
|---|---|---|
| `max_total_tokens` | 100,000 | 8,000–200,000 |
| `compaction_threshold_tokens` | 75,000（约 75%） | 1,000–200,000 |
| `context_window_tokens` | 1,000,000 | 8,000–2,000,000；模型元数据，不是轮次预算 |
| `max_steps` | 24 | 1–32 |
| `max_tool_calls_per_turn` | 20 | 1–24 |
| `max_parallel_tools` | 6 | 1–24 |
| `max_tool_result_chars` | 100,000 | 1,000–200,000 |
| `max_page_context_chars` | 6,000 | 500–50,000 |
| `max_compaction_summary_chars` | 6,000 | 1,000–20,000 |
| `max_compaction_last_user_chars` | 4,000 | 500–10,000 |
| `auto_compaction_enabled` | `true` | 布尔值 |
| `parallel_tools_enabled` | `true` | 布尔值 |
| `save_memory_requires_approval` | `true` | 布尔值；`save_memory` 需要人工审批 |

Pydantic 和匹配的 PostgreSQL 检查约束会强制执行范围以及两条
跨字段规则：压缩阈值必须低于总令牌预算，并行宽度不得超过每轮
工具调用数。上下文窗口独立于两者；更改它永远不会提高轮次预算。
应用的全局校验封装会把请求校验失败映射为 `400 invalid_request`，
而不是 422。

一次请求会在短生命周期的数据库会话中加载一个不可变的运行时快照。
活动的 SSE 运行会保留它启动时的快照；后续运行使用更改后的设置。
后端契约描述于 `backend/README.md`。

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

一个任务会经过 `queued(0)`、`parsing(5)`、`chunking(15–20)`、
`embedding(25–90)`、`summarizing(95)` 和 `ready(100)`，或以
`failed` 结束。`progress_pct`、`chunks_total` 和 `chunks_embedded`
是持久化的，因此重新加载的页面可以恢复相同的显示。暂存的文件行和
分块行只有在任务就绪时才会发布；失败的任务保留其错误，但不会暴露
任何部分的当前文件。

一个 worker 进程在空闲时每秒轮询数据库，并用
`SELECT ... FOR UPDATE SKIP LOCKED` 认领排队的行。它运行两个提取
线程、最多两个在途任务，全局异步嵌入并发为六，并批量更新进度。
崩溃后陈旧任务会被重新排队，嵌入重试是有界的。API 生命周期会为
本地使用启动一个 worker；生产环境请运行专用进程：

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

`/settings` 上的 **摄取运行时** 面板（仅 root）编辑单例
`ingest_config` 行。它是完整替换，而不是补丁；读取响应携带
`{config, defaults, source, updated_at}`，并带有 Database/Defaults
徽标。worker 可以跨账户认领任务，但每个解析、分块、嵌入和发布
步骤都在任务所有者的行级安全上下文中运行。

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
| `chunk_overlap_chars` | 500 | 0–5,000；低于目标值 |

worker 在每一轮循环和每个任务中读取新的数据库快照，因此保存的
worker 更改无需重启即可生效；已在运行的任务保留其快照。环境值用于
初始化全新安装，并保留为回退。更改分块大小只会影响未来的摄取。
后端契约描述于 `backend/README.md`。

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

`./start.sh` 是最短的裸机路径：如果 Docker 可用，它会启动开发
数据库/缓存，加载 `.secrets/deepseek.env`，同步后端，并在
<http://127.0.0.1:8000> 提供 API 和已提交的客户端。

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

这是 **Tunnel** 部署变体。未来纯 Cloudflare Serverless 部署应使用
自己的 compose 文件；tunnel 栈保留在
`docker-compose.cloudflare-tunnel.yml`。它不发布任何主机端口。
`cloudflared` 连接到非 root 的 Caddy 反向代理，后者再转发到 API。

```bash
mkdir -p secrets
# Write the tunnel token; no trailing newline.
printf '%s' 'your-tunnel-token' > secrets/cf_token.txt
chmod 644 secrets/cf_token.txt
export APSOR_PUBLIC_HOST=archive.example.com
docker compose -f docker-compose.cloudflare-tunnel.yml up -d --build
```

把 `archive.example.com` 的 tunnel 入口指向 `http://caddy:80`。
令牌文件被 gitignore。Caddy 只服务 `APSOR_PUBLIC_HOST` 指定的主机，并对
其他所有主机返回 `404`，因此不要把第二个公网主机名加入 tunnel 入口。
权限说明见
`secrets/README.md`，完整的英语部署、备份、安全和故障排除指南见
[`docs/cloudflare-tunnel.md`](docs/cloudflare-tunnel.md)。

## 工具接口

档案提供六个小型 HTTP 工具。每个 JSON 端点对应一个 Agent 可以调用的
检索或记忆操作；每个负载都被刻意做得足够小，以便 LLM 按顺序使用。

| 工具 | 端点 | 返回内容 |
|---|---|---|
| `search_knowledge` | `GET /api/v1/search?query=&result_number=2` | 来自 BM25 + 向量的每种来源类型的顶部结果，使用 RRF 融合并去重 |
| `read_file` | `GET /api/v1/files/{file_id}/chunks/{chunk}?chunk_range=1` | 一个从 1 开始的分块窗口 |
| `read_timeline` | `GET /api/v1/timeline?year=&month=&day=&day_range=1` | 每种类型最多五个采样事件、密度以及跳过计数 |
| `read_path` | `GET /api/v1/paths?path=/history&path_depth=1&fuzzy_search=` | 目录和文件，或模糊路径匹配 |
| `save_memory` | `POST /api/v1/memories` | 一条带有自动生成标题的新记忆、它取代的已弃用记忆，以及任何新摘要；省略 `content` 可在没有替代内容的情况下弃用 `supersedes` id |
| `read_memory` | `GET /api/v1/memories/{memory_id}?memory_range=1&trace_history=true` | 目标、邻居、取代关系、后继者和链条 |

持久化档案 agent 暴露九个模型工具：上述六个加上
`present_resource`、`web_search` 和 `web_fetch`。HTTP 示例使用
显式参数；HTTP 服务器默认值是 `result_number=2`、`chunk_range=1`、
`day_range=1`、`path_depth=1` 和 `memory_range=0`。文本按约 4,000
字符分块，重叠 500 字符；现有文件在重新摄取之前保留其原始分块
边界。Agent 的工具架构会选择自己的默认值，例如 `result_number=8`
和 `day_range=7`。对于外部 LLM 调用者，单独的 `/api/v1/tools/*`
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
`reason`）、`POST /api/v1/summaries`、`GET /api/v1/stats`、
`GET /api/v1/health` 和 `GET /api/v1/ai/status`。

### 文件夹工作区

`/library` 是一个文件夹优先的工作区。面包屑和文件夹栏描述你所在的
位置；主区域显示当前路径的文件夹卡片和文件卡片。之前的表格仍作为
紧凑列表视图提供，用于密集浏览，并且是窄屏幕上的回退布局。

- **新建文件夹** 会创建请求的文件夹以及任何缺失的祖先。该操作是
  幂等的：重复执行会返回同一个文件夹，状态码 `201`。
- **拖放上传** 接受从桌面拖放到文件夹卡片或当前文件夹表面的文件。
  上传使用与上传对话框相同的摄取路径、扩展名允许列表和服务器限制：
  每个上传文件 10 MB，以及 `.md`、`.markdown`、`.txt`、`.csv`、
  `.json`、`.log`、`.pdf`、`.docx`、`.jpg`、`.jpeg`、`.png` 或
  `.webp`。对话框还支持 2 MB 的纯文本创建。拖放的文件永远不会被
  打开或执行。
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
  `ui.notice` 条目。`model` 恰好是提供商负载；`data` 仅用于 UI/诊断。
- `agent_run` — 一次提交的持久化状态（`request_id`、状态、中止、
  最后条目、安全错误）。`agent_commit_seq` 对在一个事务中写入的条目
  进行分组。
- `agent_approval` — 针对需要确认的工具调用的一个持久化待处理/
  已批准/已拒绝/已过期人工决定，包括经过校验的参数、安全预览，以及
  用于恢复等待运行的循环快照。
- `agent_config` — 单例运行时配置（`id=1`），保存经过校验的令牌、
  步骤、工具、页面上下文和压缩限制。

第一个条目是冻结的 `pi.system` 提示词和工具快照。上下文构建器会
确定性地重放条目：它遵循 `head_entry_id` 和 `edits`，保留系统条目，
把工具结果直接移到其 assistant 调用之后，合成缺失的结果，丢弃孤立
结果，并排除失败的 assistant 尝试。工具调用会经过校验并作为结构化
结果返回；工具失败永远不会变成 HTTP 500。

| 方法 | 路径 | 用途 |
|---|---|---|
| `POST` | `/api/v1/agent/conversations` | 创建一个对话及其系统条目 |
| `GET` | `/api/v1/agent/conversations` | 列出活动/已归档对话，最新活动在前 |
| `GET` | `/api/v1/agent/conversations/{conversation_id}` | 元数据加上第一页条目 |
| `GET` | `/api/v1/agent/conversations/{conversation_id}/entries?after_id=&limit=` | 升序条目页 |
| `PATCH` | `/api/v1/agent/conversations/{conversation_id}` | 重命名、归档或还原 |
| `DELETE` | `/api/v1/agent/conversations/{conversation_id}` | 软删除；条目保留以供审计 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/compact` | 追加手动压缩边界 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/clear` | 追加重置边界；对话记录保留 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/fork` | 通过包含式截止点把条目复制到新线程 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/messages` | 追加用户条目并运行循环 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/retry` | 重试最近一次失败/取消的运行 |
| `GET` | `/api/v1/agent/conversations/{conversation_id}/approvals?status=` | 持久化审批，最旧在前（默认 `pending`） |
| `POST` | `/api/v1/agent/approvals/{approval_id}/approve` | 执行一次，追加工具结果，恢复 |
| `POST` | `/api/v1/agent/approvals/{approval_id}/reject` | 追加 `memory_rejected`，不写入并恢复 |
| `GET` | `/api/v1/agent/tools` | 当前工具目录以及提示词/工具版本 |
| `GET` | `/api/v1/agent/settings/system-prompt` | 列出每个系统提示词区段 |
| `POST` | `/api/v1/agent/settings/system-prompt` | 创建一个区段（`201`） |
| `PUT` | `/api/v1/agent/settings/system-prompt/order` | 重新排序每个区段 |
| `PUT` | `/api/v1/agent/settings/system-prompt/{section_id}` | 替换一个区段 |
| `DELETE` | `/api/v1/agent/settings/system-prompt/{section_id}` | 删除一个区段（`204`） |
| `POST` | `/api/v1/agent/settings/system-prompt/reset` | 用四个预置默认值替换每个区段 |

`POST /api/v1/agent/conversations/{conversation_id}/messages` 接受
`{content, request_id?, page_context?, client_timezone?,
client_utc_offset_minutes?}`，而 `.../retry` 接受 `{request_id?}`。
两者默认都流式传输 `text/event-stream`。客户端时区会与服务器渲染的
`<current_time>` 块一起存储在每个用户条目上；该块在消息文本之后
恰好追加一次。有序的系统提示词区段在创建对话时写入，并冻结到该
线程中。四个默认值作为普通行预置；设置允许 root 账户为整个部署
编辑、删除或重新排序每一行。事件名称是 `run_start`、
`message_start`、`message_delta`、`message_end`、`tool_start`、
`tool_end`、`approval_required`、`run_end` 和 `error`。`run_start`
报告 `page_context_entry_id`（或 `null`）、`page_context_attached`
和 `resumed`，以便客户端标记是否写入了新快照，以及流是否继续一个
持久化的等待运行。`tool_start` 和 `tool_end` 还携带 assistant 调用
批次的 `parallel`、`batch_size` 和 `parallel_index`。`tool_end`
携带持久化的工具结果 `data` 负载以及 `duration_ms` 和 `error_code`，
因此检查器可以在对话记录重新获取完成之前渲染预览。`message_start`
的 `entry_id=null`，因为 assistant 条目只在 `message_end` 时持久化；
增量仅用于传输。要获取完成的轮次，请发送
`Accept: application/json`。SSE 响应设置
`Cache-Control: no-cache, no-transform` 和 `X-Accel-Buffering: no`，
并且 Starlette 的 GZip 中间件排除 `text/event-stream`。

每个对话一次只允许一个活动运行。默认值允许 24 个模型步骤、每个用户
轮次 20 次工具调用、6 个并行工具、每轮 100,000 个总令牌（跨模型
步骤累计）、自动压缩前 75,000 个令牌，以及每个工具 100,000 个结果
字符。一个单独的 1,000,000 令牌模型上下文窗口记录提供商容量；它是
元数据，不会提高轮次预算或改变压缩。每个结果都会按该每结果上限
独立裁剪，并带有可见的 `[truncated]` 标记；不存在轮次范围的结果
预算，也没有第二次摘要调用。100,000 字符的上限大致跨越二十五个
4,000 字符的分块。这些是运行时设置，不是代码常量；见上文的
**Agent 运行时设置**。启用并行工具时，符合条件的工具调用会一起
启动并通过 `asyncio.gather` 执行。结果持久化和 `tool_end` 顺序遵循
assistant 调用顺序，而不是完成顺序。禁用并行工具时，执行是顺序的，
事件报告 `parallel=false`。

失败或取消的运行可以在不重复用户条目的情况下重试。当最新条目是
失败/取消的 assistant 回答、末尾的硬限制工具结果（`step_limit`、
`token_limit`、`tool_call_limit` 或
`tool_result_budget_exhausted`），或者在记录 assistant 条目之前最后
一次流失败时，聊天工作台和停靠的 agent 会显示重试操作。重试会为
同一个用户条目启动新的运行；UI 不会追加第二条消息，并在流处于活动
状态时禁用该操作。如果对话记录仍然太长，重试可能再次触及相同的
上下文或令牌预算。当最新运行已完成或并非失败/取消时，端点返回
`409 agent_run_not_retryable`；该错误之后 UI 会重新获取对话记录，
使过期的重试操作消失。

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

当 `auto_compaction_enabled` 为 true，并且在新用户轮次之前估计的
活动上下文超过 `compaction_threshold_tokens` 时，该轮次会先追加
一个 `pi.compaction` 条目：

- 该条目把 `head_entry_id` 设为自身的 id，因此较早的条目保持
  不可变，但落在新的活动上下文之外。
- 它的提供商消息以 `<compaction>` 开头，并携带 `<last_user_input>`
  （压缩前的最后一次用户输入）和 `<summary>`。
- 同一事务按压缩 → 页面上下文（当页面被重新附加时）→ 用户的顺序
  写入，因此模型会在新请求之前看到摘要。

这会启动新的 KV 缓存谱系。系统提示词和工具快照保持冻结，旧对话
记录在 `/chat` 和停靠区仍然可读。

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
时间线、记忆、搜索、仪表盘），然后是包含 **用户资料** 的个人区块，
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

文件在文件库内的就地预览模态框中打开；记忆阅读器是 `/memory/:id`
的普通路由。旧的 `/viewer/*` URL 会重定向到这些界面，因此旧引用和
书签仍然有效。

| 资源 | 渲染器 |
|---|---|
| PDF | `react-pdf` 11 + 捆绑的 `pdfjs-dist` 6，页面导航、缩放、适应宽度、文本层 |
| DOCX | 脚本禁用沙箱中的 `docx-preview` |
| 图像 | 使用标准文件内容端点的原生图像 |
| 文本 / JSON / Markdown / CSV | 带换行/复制/下载的档案页，美化 JSON，GFM Markdown |
| 记忆 | 带有谱系和追溯链接的压制记录式记忆叶 |

`GET /api/v1/files/{file_id}/content` 以内联方式提供原始文件，带有
`nosniff`、沙箱 CSP、ETag/Last-Modified，以及单范围 HTTP Range 支持
（`206`/`416`；`If-None-Match` 返回 `304`）。`/download` 仍然是
附件。纯文本记录具有 `has_original=false`；页面会完全跳过
`/content` 探测，并读取已索引的分块。

PDF.js 的 CMaps 和标准字体由 `bun run pdf-assets` 从固定版本的
`pdfjs-dist` 包复制到 `frontend/public/pdfjs/`，`dev` 和 `build` 会
自动运行它。Vite 会在构建镜像时把它们输出到 `frontend/dist/pdfjs/`，
因此会与其余产物一起打包。它们在本地提供，永远不会从 CDN 获取。

### 账户、角色与会话

首次访问时，应用会要求你创建 root 账户。没有默认密码，也没有电子
邮件恢复。root 随后可以从 **账户** 创建普通账户；新账户会使用生成
的 20 字符临时密码创建，该密码只显示一次，并且它必须在加载任何
档案内容之前选择新密码。root 可以禁用、启用、重置和模拟其他账户。
禁用账户或重置其密码会撤销其会话；撤销在请求开始时检查，因此已经
在流式传输的 SSE 轮次可能会完成其当前运行。账户永远不会被删除，
因此用户名会一直保留。

**账户** 现在使用更大的信息卡片。每张卡片包含头像、名称和
`@username`、角色/状态徽标、创建日期、最近登录，以及该账户汇总的
agent 用量：总令牌、提示词令牌、补全令牌和缓存令牌、API 调用、轮次以及最近
活动。提示词/补全的拆分绘制成一个小条，没有 agent 活动的账户仍会
显示可读的零状态。用量按 agent 运行计数，并由数据库触发器汇总，
因此卡片仍然是一次廉价的 root 专用列表读取，而不是跨账户对话扫描。

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
只显示 **常用提示词** 和 **语言**，而 root 看到全部八个标签。仪表盘
和统计计数限定在登录账户内；AI 状态是全局且只读的。密码使用 Argon2
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
  说明 + OCR；否则使用由文件名派生的说明文字，并带有
  `extraction_method=filename`。图像仍然是普通的文件库文件。
- **PDF** — 先使用 pypdf 文本；当文本为空、乱码，或 AI 结构化分析
  表示 `use_vision` 时，使用 pypdfium2 渲染最多 10 页并运行视觉 OCR。
- **DOCX** — python-docx 段落和表格；嵌入图像可以提供视觉回退。
- **TXT / MD / CSV / JSON / LOG** — 直接文本加上 AI 结构化元数据
  （标题、摘要、标签、document_type）。

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
5. **融合**：使用倒数排名融合。每种来源类型保留自己的顶部
   `result_number`，因此摘要不会被文件分块挤掉。
6. **去重**：按分块 id 去重，然后填充文件、记忆或摘要行。

如果向量召回不可用，搜索仍然返回 BM25 结果。当嵌入调用在重试预算
内失败时，同步摄取会让分块保持纯文本；持久化 worker 会把耗尽嵌入
重试视为任务失败，因此不会发布部分文件。

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
memory_summary ───┘
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
  `raw_file_path`。`storage_backend` 记录原始字节的 `local` 或 `r2`，
  并且当且仅当 `storage_key` 为 null 时为 null。
- `folder`：显式的文件夹记录（`parent_id`、`path`、`name`、
  `depth`）。空文件夹和文件夹身份独立于文件而存在。唯一性按账户：
  `(user_id, path)`。
- `chunk`：`(source_kind, source_id, chunk_index)`，带有一个可选的
  JSONB 向量。
- `chunk_ngram`：BM25 使用的倒排索引。
- `memory`：线性时间线，带有自动生成的 `title`、`supersedes_ids`、
  `superseded_by_id`、`status=active|deprecated`，以及直接停用的来源
  信息 `deprecated_at` / `deprecated_reason`。已弃用的行必须有一个
  后继者或一个 `deprecated_at` 时间戳。
- `memory_summary`：周期、源记忆 id、主题、生成器和模型。
- `chat_provider_config` / `embedding_provider_config` /
  `web_search_provider_config` / `web_fetch_provider_config`：每个
  已保存提供商一行，带有加密的 API 密钥、安全提示，以及模型/基础
  URL/维度。`is_active` 上的部分唯一索引强制每种能力只有一行活动
  记录。`web_search` 和 `web_fetch` 是独立的凭据。
- `app_user`：每个账户一行。`role` 是 `root` 或 `user`；`is_active`、
  `must_change_password`、`disabled_at`、`created_by_user_id` 以及
  密码审计时间戳描述账户生命周期。部分唯一索引强制恰好一个 root，
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
  经过校验的运行时限制。
- `saved_question`：账户的问答库。`question` 由用户撰写；`answer`、
  `citations`、`conversation_id` 以及运行状态/错误字段只由提问写入。
  `conversation_id` 使用 `ON DELETE SET NULL`，`last_asked_at` 记录
  最近一次尝试。
- `file_ingest_job`：持久化摄取队列。它存储源类型、路径、负载键和
  后端、状态/阶段、`progress_pct`、分块计数、有界错误字段以及尝试/
  时间戳。每个账户的一条路径只能有一个活动任务。任务指向其暂存
  文件，失败时清除该链接，并且只有任务发布文件时，文件及其分块才会
  成为当前。
- `ingest_config`：一行（`id=1`），带有经过校验的 worker 轮询、
  提取、在途、嵌入和分块大小设置。它不是分块来源；队列引用最终
  发布的文件。

原始字节不存储在 PostgreSQL 中。它们位于本地磁盘或私有 R2 存储桶
中，由每个文件的 `storage_backend` 选择；提取的分块及其 n-gram
保留在 PostgreSQL 中。

已提交的代码、注释、UI 文案和文档均为英语。

## 开发检查

```bash
# Backend
cd backend
uv run ruff check .
uv run mypy app
PYTHONUTF8=1 uv run bandit -r app -c pyproject.toml
uv run pip-audit
PYTHONUNBUFFERED=1 uv run pytest -q 2>&1 | tee /tmp/apsor-archive-pytest.log

# Frontend
cd frontend
bun run lint
bun run typecheck
bun run build
bun audit
```

集成测试套件在同一实例上使用一个真实的 PostgreSQL 测试数据库
（`apsor_archive_test`），顺序运行，并在测试之间重置每张被跟踪的表。
数据库由 `alembic upgrade head` 构建，而不是 `create_all`，因此
`apsor_app` 角色、授权和 RLS 策略在每个请求中都存在。共收集 46 个
测试；每个测试都会演练真实的 HTTP 接口和数据库。多用户测试覆盖
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

最新的迁移是 `f9c2a7d4e6b1`，位于 `e8f1c4d2a7b9` 之后。此分支上
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
- `f9c2a7d4e6b1`（当前 head）向 `agent_run` 添加每次运行的令牌/API
  调用计数器，向 `app_user` 添加每账户汇总、用量增量触发器，以及
  可空的 `user_session.impersonator_user_id` 模拟标记。它从
  assistant 条目 JSON 回填历史用量，并且强制 RLS 回填需要
  superuser/BYPASSRLS 迁移角色。

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
    module/web_research/        Tavily search/fetch service, URL safety, cache
  alembic/                      migrations
  tests/                        46 integration tests
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
    library/                    files, media gallery, preview modal, intake
    home/ search/ timeline/ memory/ about/ ...
  src/apis/fetch-client.ts      the only JSON mutator
  src/apis/agent-stream.ts      SSE transport for agent turns
  src/lib/                      formatting and safe highlighting
  src/styles/                   paper / night archive tokens
  scripts/copy-pdfjs-assets.mjs copies pinned PDF.js CMaps/fonts
  dist/                         generated build output, gitignored
docker-compose.yml              normal deployment
docker-compose.dev.yml          local dependencies
docker-compose.cloudflare-tunnel.yml   Cloudflare Tunnel deployment
docs/cloudflare-tunnel.md       Tunnel deployment, backup, and security guide
docker/caddy/                   non-root reverse proxy for the tunnel
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
- 常规 Compose 文件把 API 绑定到 `127.0.0.1`；Cloudflare 文件不
  发布任何主机端口。登录限流在内存中，因此是单进程的；请运行一个
  API 进程，或在横向扩展前把限流迁移到 Valkey。
- 路径会拒绝遍历段、反斜杠、控制字符和过长的值。上传限制为 10 MB，
  并受扩展名允许列表限制。
- 来自文件和记忆的 HTML 通过 React 作为文本渲染。Agent Markdown
  使用 `skipHtml`；DOCX 预览在禁用脚本的沙箱中运行。UI 从不使用
  `dangerouslySetInnerHTML`。
- DeepSeek 密钥位于 `.secrets/deepseek.env` 或环境中。它永远不会被
  记录、返回或提交。从设置页面保存的密钥在 PostgreSQL 中加密，并且
  只作为四字符提示返回。
- R2 凭据位于被 gitignore 的 `.secrets/r2.env`，以只读方式挂载，
  永远不会成为容器环境变量。存储桶是私有的，没有预签名或公开 URL。
- 摘要和 agent 轮次会发生 AI 调用。如果提供商失败，API 会返回稳定
  的错误，而不是编造答案。

## 许可证

MIT。见 `LICENSE`。
