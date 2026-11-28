# 部署

[English](../deployment.md) · **繁體中文** · [简体中文](../zh-CN/deployment.md)

## 快速開始

### Docker Compose（正式環境）

正式堆疊是 **Cloudflare Tunnel → Caddy → API + 資料匯入 worker**，並在私人的
Compose 網路上執行 PostgreSQL、Valkey、RabbitMQ，以及（預設）隨附的 RustFS
物件儲存。它不發布任何主機連接埠。

請執行設定精靈，而不是手動撰寫環境變數：

```bash
./start.sh setup        # or: make setup
mkdir -p data && sudo chown -R 10001:10001 data
docker compose up -d --build
```

精靈會詢問公開主機名稱、儲存後端（預設為隨附的 **RustFS**，也可選
Cloudflare R2、任何 S3 相容端點或本機磁碟）、工作階段時效、選用的 DeepSeek
金鑰，以及 Cloudflare Tunnel 權杖。它會寫出非祕密的 `.env`，產生 RustFS 與
RabbitMQ 憑證，把貼上的金鑰存進 `.secrets/*.env` 與 `secrets/*.txt` 且不回顯，
除非你確認覆寫，否則保留任何既有檔案，並印出容器讀取祕密檔案所需的
`sudo chgrp` 指令。`./setup.sh --defaults` 以非互動方式執行同一流程（正式環境
搭配 RustFS）；加上 `--dev` 則寫出開發用的 `.env`。

將 Cloudflare Tunnel 的公開主機指向 **HTTP `caddy:80`**，再開啟
`https://$APSOR_PUBLIC_HOST`。請把 `APSOR_PUBLIC_HOST` 放進 `.env`，重啟後
才能保留主機比對設定。第一次造訪時會要求你建立 root 帳號。root 接著可以從
**帳號** 建立一般帳號；每個新帳號會收到一組一次性臨時密碼，並且必須在第一次
登入時變更。新帳號也會繼承部署的主要對話端點與模型，因此對話與背景 AI 可
立即使用；若部署沒有任何使用中的對話端點，帳號會保持未指派，root 必須先
指派。PostgreSQL 使用具名磁碟區；本機的原始位元組與產生的祕密金鑰位於主機的
`./data` 目錄下。原始檔案位元組會寫入精靈所選的後端；請見
[物件儲存](#物件儲存rustfsr2s3-或本機)。

> 注意：`./data` 會綁定掛載到容器中，且容器程序以 uid `10001` 執行。請在
> 第一次開機前建立目錄並修正其擁有者，否則上傳與原始位元組寫入都會失敗。
> 若主機使用者已經是 uid `10001`，可以略過 `sudo chown`。

`postgres-data` 磁碟區固定使用明確的實體名稱：`docker-compose.yml` 為
`apsor-archive_postgres-data`，`docker-compose.dev.yml` 為
`apsor-archive-dev_postgres-data`，因此重新命名 Compose 專案不會讓資料庫成為
孤兒。在此次更名之前建立的堆疊使用了不同的實體磁碟區名稱，所以請在啟動前
將該磁碟區的內容複製到新的磁碟區（或在本機 Compose 檔案中保留舊名稱）。
否則 PostgreSQL 會初始化一個空資料庫。

Docker 建置會在前端階段從 `frontend/` 編譯前端，因此變更前端程式碼後
直接執行 `docker compose up --build` 即可，不需要手動建置。只有在想在本機
預覽時才需執行 `cd frontend && bun run build`。

若要啟用 AI 回答與 AI 摘要：

```bash
mkdir -p .secrets
printf 'APSOR_DEEPSEEK_API_KEY=sk-your-key\n' > .secrets/deepseek.env
chmod 755 .secrets
sudo chgrp 10001 .secrets/deepseek.env
chmod 640 .secrets/deepseek.env
docker compose up -d --build
```

Compose 檔案會以唯讀方式掛載 `.secrets/`。應用程式自行讀取該環境檔，因此
金鑰永遠不會成為容器環境變數，也永遠不會出現在 `docker compose config`
中。API 容器以 uid `10001` 執行，因此該檔案必須能被這個 uid 讀取：群組
`10001` 搭配權限 `640`，或在單一使用者的主機上使用 `644`。金鑰已列入
gitignore，且 API 永遠不會傳回它。
沒有金鑰時，摘要會退回確定性的抽取式形式，圖片上傳會使用檔名圖說，代理
訊息則傳回 `503 agent_not_configured`。

### 物件儲存（RustFS、R2、S3 或本機）

`APSOR_STORAGE_BACKEND` 決定新原始位元組的預設寫入位置。設定精靈會設定它；
除了 `local` 之外，所有選項都使用同一個 S3 相容轉接器。

| 值 | 位元組寫入位置 | 憑證 |
|---|---|---|
| `rustfs` | 隨附的 RustFS 服務（以 `COMPOSE_PROFILES=rustfs` 啟動）。新安裝的預設值。 | 由精靈產生到 `.secrets/s3.env` 與 `secrets/rustfs_*_key.txt` |
| `r2` | 私人的 Cloudflare R2 儲存桶 | `.secrets/r2.env` |
| `s3` | 任何 S3 相容端點（AWS S3、MinIO、另一個 RustFS） | `.secrets/s3.env` |
| `local` | `APSOR_DATA_DIR`；開發與測試的預設值 | 無 |
| `auto` | `.secrets/r2.env` 完整時用 R2，否則用 S3，再否則用本機 | — |

`rustfs` 是 `s3` 的別名。未設定 `APSOR_STORAGE_BACKEND` 時，正式環境的 Compose
檔案會使用 `auto`，因此既有的 R2 部署不必修改 `.env` 就會繼續寫入 R2。每筆
資料列會記錄保存其位元組的後端（`local`、`r2` 或 `s3`），而設定完整的每個後端
都保持可讀，因此分階段移轉期間可以服務混合的典藏。

非祕密設定放在 `.env`：

- R2：`APSOR_R2_ENDPOINT_URL`（`https://<account-id>.r2.cloudflarestorage.com`，
  沒有預設值）、`APSOR_R2_BUCKET`（`apsor-archive`）、`APSOR_R2_REGION`
  （`auto`）、`APSOR_R2_PREFIX`。
- S3／RustFS：`APSOR_S3_ENDPOINT_URL`（Compose 預設 `http://rustfs:9000`）、
  `APSOR_S3_BUCKET`（`apsor-archive`）、`APSOR_S3_REGION`（`us-east-1`）、
  `APSOR_S3_PREFIX`、`APSOR_S3_ADDRESSING_STYLE`（`path` 或 `virtual`），以及
  `APSOR_S3_CREATE_BUCKET`（第一次寫入時建立缺少的儲存桶；隨附的 RustFS 需要它）。

存取金鑰絕不放進 `.env` 或容器環境變數。Compose 會以唯讀方式掛載
`.secrets/`，由應用程式自行讀取 `r2.env`／`s3.env`；RustFS 容器則以 Docker
secrets 讀取自己的金鑰組。它們都以 uid `10001` 執行，因此這些檔案需要群組
`10001` 與權限 `640`（精靈會印出 `sudo chgrp` 指令）。儲存桶保持私人：沒有
預先簽署 URL、沒有公開存取，且 `files/` 沒有生命週期到期設定。
`data/.secret_key` 是 Fernet 主金鑰，只留在本機；請與 PostgreSQL 分開備份。
請把 `apsor-archive_rustfs-data` 磁碟區（或外部儲存桶）與資料庫一起備份為
同一組備份。

若要將現有典藏從本機磁碟移至 R2，請停止 API 與 worker，並從 `backend/`
執行儲存 CLI：

```bash
uv run python -m script.migrate_storage_to_r2 --dry-run
uv run python -m script.migrate_storage_to_r2 --copy
uv run python -m script.migrate_storage_to_r2 --verify
# only after a verified backup and rollback window
uv run python -m script.migrate_storage_to_r2 --delete-local
```

`--copy` 會上傳並驗證大小與 SHA-256，然後將對應的 `file` 與可重試的
`file_ingest_job` 資料列標記為 `storage_backend='r2'`。請將 PostgreSQL
傾印、資料目錄備份與 R2 儲存桶內容一起保存為同一組備份。請以版本控制或
物件同步工作來備份儲存桶；軟刪除的檔案仍保留其物件。

### Cloudflare Tunnel

正式 Compose 堆疊已包含 `cloudflared`、Caddy 與 API。請在 Cloudflare
儀表板新增一個公開主機：

- **Service type**：`HTTP`
- **URL**：`caddy:80`

`cloudflared` 主動向外連線，因此不需要路由器連接埠轉送。Caddy 只服務
`APSOR_PUBLIC_HOST` 指定的主機，並對其他所有主機回應 `404`；請勿在 tunnel
ingress 加入第二個公開主機名。權杖權限請見 `secrets/README.md`，完整的英文
部署、備份、安全性與疑難排解指南請見
[`docs/cloudflare-tunnel.md`](../../docs/cloudflare-tunnel.md)。

### 家用網路（不使用 Tunnel）

想在自己的電腦或家用網路上試用時，可以略過 Tunnel，讓 Caddy 直接開放 8080 埠：

```bash
./start.sh setup                     # 選擇 "production"；Tunnel 權杖留空即可
# 在 .env 把 APSOR_PUBLIC_HOST 設成你在瀏覽器輸入的名稱，
# 例如：APSOR_PUBLIC_HOST=localhost
docker compose -f docker-compose.yml -f docker-compose.local.yml up -d --build
```

接著打開 `http://localhost:8080`（或 `http://<那個名稱>:8080`）。覆寫檔
`docker-compose.local.yml` 會關閉 Tunnel 連接器，並讓登入 Cookie 在一般 HTTP 下也能運作。
想換埠號，在 `.env` 設定 `APSOR_LOCAL_PORT`。凡是會從網際網路連進來的部署，都請改用 Cloudflare Tunnel。

### Docker Swarm

`docker-stack.yml` 會在單一節點的 Swarm 上執行同一組服務。Swarm 不會自己建置映像檔，
也不會讀取 `.env`，所以要先用 Compose 建置，再把 `.env` 載入 shell：

```bash
./start.sh setup                     # 只需一次：寫入 .env 與 secret 檔
docker compose build                 # 標記 apsor-archive-api、-worker 與 -caddy
docker swarm init                    # 只需一次，若這台機器還不是 manager
set -a; . ./.env; set +a
docker stack deploy -c docker-stack.yml apsor
docker stack services apsor          # 看著服務一一啟動
```

所有服務都固定在 manager 節點上，因為檔案館資料、`.secrets/` 資料夾和訊息佇列設定，
都是掛載自這台機器的路徑。Swarm 會忽略 `depends_on`，所以 API 和 worker 會自動重啟，
直到 PostgreSQL 準備好（通常一分鐘內）。RustFS 一定包含在 stack 裡；如果你的檔案存在
Cloudflare R2 或其他 S3 服務，執行 `docker service scale apsor_rustfs=0` 即可。
要更新時，拉下新的程式碼，再執行一次 `docker compose build`，然後重跑 `docker stack deploy` 那一行。
