# 部署

[English](../deployment.md) · [繁體中文](../zh-TW/deployment.md) · **简体中文**

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

### Cloudflare Tunnel

生产 Compose 栈已包含 `cloudflared`、Caddy 和 API。请在 Cloudflare
仪表板添加一个公开主机：

- **Service type**：`HTTP`
- **URL**：`caddy:80`

`cloudflared` 主动向外连接，因此不需要路由器端口转发。Caddy 只服务
`APSOR_PUBLIC_HOST` 指定的主机，并对其他所有主机返回 `404`；不要把第二个
公网主机名加入 tunnel 入口。令牌权限见 `secrets/README.md`，完整的英文
部署、备份、安全与疑难解答指南见
[`docs/cloudflare-tunnel.md`](../../docs/cloudflare-tunnel.md)。

### 家庭网络（不使用 Tunnel）

想在自己的电脑或家庭网络上试用时，可以跳过 Tunnel，让 Caddy 直接开放 8080 端口：

```bash
./start.sh setup                     # 选择 "production"；Tunnel 令牌留空即可
# 在 .env 中把 APSOR_PUBLIC_HOST 设为你在浏览器里输入的名称，
# 例如：APSOR_PUBLIC_HOST=localhost
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

然后打开 `http://localhost:8080`（或 `http://<该名称>:8080`）。覆盖文件
`docker-compose.local.yml` 会关闭 Tunnel 连接器，并让登录 Cookie 在普通 HTTP 下也能工作。
想更换端口，在 `.env` 中设置 `APSOR_LOCAL_PORT`。凡是会从互联网访问的部署，都请改用 Cloudflare Tunnel。

### Docker Swarm

`docker-stack.yml` 会在单节点 Swarm 上运行同一组服务。Swarm 不会自己构建镜像，
也不会读取 `.env`，所以要先用 Compose 构建，再把 `.env` 载入 shell：

```bash
./start.sh setup                     # 只需一次：写入 .env 和 secret 文件
docker compose build                 # 生成 apsor-archive-api、-worker 和 -caddy 镜像
docker swarm init                    # 只需一次，如果这台机器还不是 manager
set -a; . ./.env; set +a
docker stack deploy -c docker-stack.yml apsor
docker stack services apsor          # 查看服务逐个启动
```

所有服务都固定在 manager 节点上，因为档案馆数据、`.secrets/` 目录和消息队列配置，
都是挂载自这台机器的路径。Swarm 会忽略 `depends_on`，所以 API 和 worker 会自动重启，
直到 PostgreSQL 就绪（通常一分钟内）。RustFS 始终包含在 stack 中；如果你的文件存放在
Cloudflare R2 或其他 S3 服务，执行 `docker service scale apsor_rustfs=0` 即可。
更新时，拉取新代码，再执行一次 `docker compose build`，然后重新运行 `docker stack deploy` 那一行。
