# 開發

[English](../development.md) · **繁體中文** · [简体中文](../zh-CN/development.md)

### 本機開發

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

開發資料庫是 `127.0.0.1:55432` 上的 PostgreSQL，角色為 `apsor`，資料庫為
`apsor_archive`
（`postgresql+psycopg://apsor:apsor@127.0.0.1:55432/apsor_archive`）。Vite
執行於 <http://127.0.0.1:5173>，並將 `/api` 代理至 API。若要建置容器所
服務的用戶端：

```bash
cd frontend && bun run build
```

`./start.sh` 是最短的裸機路徑。先執行一次 `./start.sh setup --dev` 寫出開發用
的 `.env`（預設為本機儲存），之後 `./start.sh` 會在 Docker 可用時啟動開發
資料庫／快取、同步後端，並在 <http://127.0.0.1:8000> 執行 API，同時啟動專用的
資料匯入 worker；按 Ctrl+C 會同時停止兩者。設定 `APSOR_START_WORKER=false`
則只執行 API。第一次裸機啟動前，請先執行一次 `cd frontend && bun run build`。
若要在本機試用 S3 路徑，請在精靈中選擇 `rustfs`，並以
`docker compose -f docker-compose.dev.yml --profile rustfs up -d` 啟動開發用的
儲存服務。

在 Windows 上，`./start.sh` 需要 bash shell。`./run-local.ps1` 是 PowerShell
的對等版本：若 Docker 可用，它會啟動開發資料庫／快取、同步後端，並提供
相同的 URL。應用程式會自行讀取 `.secrets/`，因此指令碼不會匯出那些值。
它也會強制使用 `SelectorEventLoop`，因為 psycopg 的非同步模式會拒絕
uvicorn 在 Windows 上預設選用的 `ProactorEventLoop`。

```powershell
.\run-local.ps1            # http://127.0.0.1:8000
.\run-local.ps1 -Port 8080
```

### 產生的 API 用戶端與漂移

儲存庫同時提交 `frontend/openapi.json` 與產生的
`frontend/src/app/generated-apis-types/` 用戶端。因此全新複製的儲存庫與
Docker 建置都能在沒有執行中後端的情況下運作。若要變更契約：

```bash
cd backend && uv run python -m script.export_openapi
cd ../frontend && bun run api:generate
```

若要檢查已提交的用戶端是否與後端相符：

```bash
make api-check
```

它會重新匯出結構描述、重新產生用戶端，並在任何差異時失敗。這保留了已
提交用戶端的便利性，同時不讓它無聲地漂移。結構描述目前宣告 79 條路徑。
除非契約變更是刻意的，操作 ID 會保持穩定。已提交的用戶端包含帳號、
變更密碼與僅限 root 的帳號操作；資料夾、移動與複製操作；頁面脈絡的
請求／詳細資料／項目種類契約；代理執行階段設定；對話壓縮／清除操作；
儲存問題的 CRUD／提問操作；以及非同步匯入工作與匯入設定的操作。檔案庫
看板、設定面板、問題簿、帳號目錄與對話工作台都會直接呼叫產生的 hook。

### 載入真實語料

Wikipedia 載入器會演練與 UI 相同的匯入路徑：

```bash
cd backend
uv run python -m script.ingest_wikipedia \
  --lang en --titles Automobile Dendrochronology \
  --prefix /wikipedia/en
```

從 `/chat` 的代理工作台跨匯入的語料提問，或將問題儲存到 `/questions`
的問題庫，之後再執行。

### 長文件驗證

儲存問題流程也曾針對一部完整長篇中文小說進行手動演練。這是驗證範例，
不是已提交的固定樣本或測試：

- 來自 Project Gutenberg 的《紅樓夢》，約 2.66 MB。
- 以 4,000 字元分塊、500 字元重疊匯入：268 個分塊。
- 真實的 `deepseek-flash` 回合回答了關於寶玉與黛玉前世情債與還淚之誓、
  石頭下凡與第一章的通靈寶玉，以及寶玉隨僧道而去的結局等問題。
- 答案帶有 `[file:27#...]` 之類的引用；在目前的工具結果限制下，沒有
  回報任何截斷。

另一項手動檢查演練了可持久化佇列。工作依序推進 `queued`、`parsing`、
`chunking`、帶有 `Embedding x / y` 計數的 `embedding`、`summarizing` 與
`ready`；檔案在就緒之前不會出現在搜尋中。在設定中儲存的 worker 變更值
會由下一個 worker 迴圈讀取，無需重新啟動，而變更的分塊目標只會影響後續
的匯入。

整合測試套件仍不依賴供應商，且未以此語料擴充。

## 開發檢查

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

`make lint` 是架構與安全性閘門：ruff、mypy、讓路由器、服務、領域程式碼與
各切片守在自身層級內的 import-linter 契約、bandit、ESLint、TypeScript、i18n
鍵值一致性，以及前端工作區邊界檢查。分支遵循 Gitflow：`feat/*` 與 `fix/*` 從
`develop` 建立並透過 pull request 合併回去，`develop` 再合併到 `main` 進行發佈。

整合測試套件在相同執行個體上使用一個真實的 PostgreSQL 測試資料庫
（`apsor_archive_test`）、依序執行，並在每次測試之間重設每張受追蹤的
資料表。資料庫是由 `alembic upgrade head` 建置，而不是 `create_all`，
因此 `apsor_app` 角色、授權與 RLS 原則會出現在每個請求中。每項測試都會
演練真實的 HTTP 介面與資料庫。多使用者測試涵蓋 root／
使用者生命週期、強制變更密碼、一次性臨時密碼、停用／重設造成的工作階段
撤銷、僅限 root 的帳號與全域設定、跨檔案／資料夾／記憶／摘要／對話／
問題／提示詞的私人典藏隔離、每帳號提示詞上限、直接 SQL 的 RLS 拒絕、
`commit_and_reapply` 在檢查點後恢復範圍化脈絡、每回合用量計算與格式
錯誤的完成內容上限、帳號用量彙總、模擬往返、root 密碼重新驗證，以及
root 密碼輪替撤銷模擬工作階段。代理測試涵蓋執行階段設定預設值、完整
PUT／重設、驗證、後續執行使用的執行階段快照、自動與手動壓縮、清除、
邊界處的頁面脈絡重新附加、重試、平行／循序工具執行、人工儲存記憶核准
（核准前不寫入、重新啟動後存活、恰好一次核准、拒絕、孤兒／已封存的
封閉式失敗復原）、核准切換（預設等待路徑、關閉時由後端直接授權寫入，
以及待處理資料列在切換後存活）、儲存的問題庫、兩個唯讀網路工具（包含
頁面模式遍歷與長行折行），以及壓縮摘要 XML。供應商涵蓋範圍會為每種
能力建立多個儲存資料列、證明部分唯一的使用中索引、清除金鑰且絕不傳回
明文、測試注入的供應商探查，並驗證身分 ID 在刪除後不會重複使用。提示詞
涵蓋範圍會建立、列出、更新、依 `sort_order` 排序、上限為 20 列，並刪除
常用提示詞。檔案庫測試也會在沒有視覺供應商的情況下上傳圖片，並驗證檔名
圖說、已儲存的原始檔、路徑清單與搜尋結果；其 R2 案例會以假用戶端演練
轉接器，並在沒有網路存取的情況下檢查缺少物件的轉譯。

最新的移轉是 `e7b2d5a9c4f1`。此分支上 `agent_config` 之後的移轉為：

- `f3c8d5a1b7e2` 移除整回合的工具結果預算；
- `a6e2f9c4d1b8` 將單一結果的工具字元上限提高至 100,000；
- `c9f1a2b3d4e5` 將 `max_total_tokens` 提高至 100,000，並將
  `compaction_threshold_tokens` 提高至 75,000；
- `b7d2e9c4a1f6` 建立 `saved_question` 及其對話外鍵／索引；
- `e2b7c4d9a6f1` 將 `max_steps` 預設值從 8 提高至 24，並更新一列未經
  修改的預設資料列；
- `d1e2f3a4b5c6` 建立 `file_ingest_job`，附狀態／來源／範圍檢查、
  使用中路徑唯一索引與檔案外鍵；
- `d4b8e6f1a2c7` 建立單例 `ingest_config`、強制其範圍與重疊規則，並
  植入資料列 `1`；
- `b3e5c7d9f1a2` 將 `context_window_tokens` 加入 `agent_config`，伺服器
  預設為 1,000,000，並附 8,000–2,000,000 的檢查條件約束；
- `c8f2a4b6d9e1` 將非 null 的 `save_memory_requires_approval` 布林值加入
  `agent_config`，伺服器預設為 `true`；現有資料列會收到 `true`；
- `f2b3c4d5e6a7` 建立 `agent_approval`，附狀態檢查、對話／執行／項目
  外鍵、狀態索引，以及部分唯一的待處理 `(run_id, tool_call_id)` 索引；
- `8f4b2c6d9e01` 移除已淘汰的 `media_ngram` 與 `media_asset` 資料表。
  其降級會重建原始的媒體結構描述；
- `c4d8e2f6a1b9` 建立明確的 `folder` 資料表，從 `tree_node` 連同 ID
  複製目前的資料夾資料列，並移除 `tree_node`。檔案葉現在衍生自
  `file.raw_file_path`。降級會重建目前的資料夾資料列與目前的檔案葉；
- `d5e9f3a7b2c1` 為 root 撰寫的第一個系統區段建立單例
  `system_prompt` 資料表；
- `e1a2b3c4d5f6` 將 `ai_provider_config` 拆成四張能力資料表
  （`chat_provider_config`、`embedding_provider_config`、
  `web_search_provider_config`、`web_fetch_provider_config`）、複製現有
  的對話／嵌入資料列，並建立每張資料表的部分唯一使用中索引；
- `a3f7c9d1e5b2` 建立 `frequently_used_prompt`，並植入三個原本硬編碼在
  對話空白狀態中的捷徑；
- `b8d2e4f6a1c3` 在 Apsor Archive 更名後，將 `dendro-hash-384` 分塊
  重新標記為 `apsor-hash-384`；
- `c9e1f3a5b7d2` 以有序的 `system_prompt_section` 資料列取代單例
  `system_prompt` 資料表，並將現有提示詞複製為第一個區段；
- `f4a1c7d9e2b3` 加入 `memory.title`（從內容回填）、
  `deprecated_at` / `deprecated_reason`、`system_prompt_section` 上供
  可編輯內建覆寫使用的 `builtin_key`，以及 `app_user.display_name` /
  `bio`。舊的「已汰除必須有後繼者」檢查會變成「後繼者或直接汰除時間
  戳記」。降級會以 `NOT VALID` 重新加入舊檢查，讓直接汰除的資料列得以
  保留；
- `b7e2d4f6a8c1` 建立具有有序標題／內容資料列的 `user_profile_card`、
  將現有的 `app_user.bio` 移轉為 `About` 卡片，並移除單一的 bio 欄位；
- `e5c1a9d3b7f2` 將自訂區段與內建覆寫統一成單一
  `system_prompt_section` 資料表。升級會將生效的內建本文具體化為一般
  資料列，排在自訂資料列之後、刪除覆寫資料列，並移除 `builtin_key` 及
  其條件約束。所有資料列現在都可編輯、刪除與重新排序；`reset` 會以四個
  初始預設值取代整個集合；
- `b8f4c2d9e6a1` 將 `max_tool_calls_per_turn` 預設值從 6 提高至 20，並
  提升一列未經修改的已儲存預設資料列；
- `e8f1c4d2a7b9` 為每張私人資料表加入 `user_id` 擁有權、複合
  `(id, user_id)` 系譜外鍵、每帳號唯一索引、
  `file.storage_backend` / `file_ingest_job.storage_backend`、單一 root
  的部分唯一索引，以及 `role` / `is_active` / `must_change_password`
  帳號欄位。它會將現有資料列回填至最舊的帳號、建立非登入的 `apsor_app`
  角色、從該角色撤銷 `alembic_version`，並在私人資料表上啟用附擁有者
  原則的強制 RLS，在全域設定資料表上啟用讀取／root 寫入原則。驗證
  資料表留在 RLS 之外；
- `f9c2a7d4e6b1` 將每次執行的權杖／API 呼叫計數器加入
  `agent_run`、將每帳號彙總加入 `app_user`、加入用量差值觸發程序，以及
  可為 null 的 `user_session.impersonator_user_id` 模擬標記。它會從助理
  項目的 JSON 回填歷史用量，且強制 RLS 回填需要超級使用者／BYPASSRLS
  的移轉角色；
- `a4c8e2f6b9d1` 移除 `max_total_tokens` 欄位及其檢查條件約束、修復未低於
  脈絡視窗的壓縮門檻，並以
  `compaction_threshold_tokens < context_window_tokens` 取代舊門檻規則。
  降級會還原 100,000 權杖上限，並在儲存門檻需要時提高該上限；
- `a1c3e5f7b9d2` 將壓縮門檻範圍提高到 1,000,000 權杖。降級會先將儲存值夾回
  200,000，再還原舊檢查條件；
- `c2f6a8d4e1b3` 將 `ingest_config.vision_description_language`
  新增為非 null 的 `varchar(80)`，伺服器預設為 `English`，並附去除空白後
  的長度檢查。降級會移除檢查條件與欄位；
- `f7a3c2d9e1b4` 新增可為 null 的
  `ingest_config.vision_image_prompt` / `vision_document_prompt` 範本、
  `file` 提示詞指紋欄位，以及 `file_ingest_job.source_file_id` 與其
  擁有者安全的複合外鍵、重新匯入檢查、使用中來源唯一索引與查詢索引。
  它不會植入或回填提示詞／指紋值。降級會先移除重新匯入工作，再還原舊的
  來源種類檢查；
- `a4c9e2f7b1d6` 新增八個 `app_user` 指派欄位與兩個指向
  `chat_provider_config` 的 `ON DELETE SET NULL` 外鍵、七項檢查條件、
  `chat_provider_config.max_output_tokens`（256–131,072）、允許 `anthropic`
  的較寬對話供應商檢查，以及四個新的 `agent_config` 欄位
  （`compaction_prompt`、`compaction_max_output_tokens`、
  `model_escalation_enabled`、`agent_max_output_tokens`）。它會把最低的
  使用中非 `none` 對話資料列及其模型回填到尚未指派的帳號；若沒有這種
  資料列，每個帳號都會保持未指派。升級後建立的新帳號也會繼承同一個主要
  端點與模型；只有在沒有使用中的對話資料列時才會保持未指派。`app_user`
  仍在 RLS 之外，因此不需要
  變更原則或授權。降級會移除指派欄位，並在仍有 `anthropic` 資料列時
  拒絕還原較窄的供應商檢查；
- `d8f2a6c4e1b9` 移除 `agent_config.max_steps` 與
  `agent_config.max_tool_calls_per_turn` 及其檢查條件，以及
  `parallel_within_tool_calls` 關係，因此工具密集的回合會持續執行到模型回答
  為止。並行上限 `max_parallel_tools` 保留。降級會還原兩個欄位，並把還原的
  呼叫上限提高到至少 `max_parallel_tools`；
- `c3e7a1f5b9d2` 放寬 `file`、`file_ingest_job` 與 `agent_chat_attachment`
  上的 `storage_backend` 檢查，允許 `s3`（RustFS、AWS S3、MinIO）；`rustfs`
  只是設定別名，`r2` 仍是獨立的值。降級會還原只有兩個值的檢查，且在仍有
  資料列記錄 `s3` 時失敗；
- `c7a3e9f1d5b2` 建立私人的 `file_thumbnail` 資料表：每個檔案
  版本一張極小的 WebP（最多 32 KiB、512 px）、指向 `file` 且帶
  `ON DELETE CASCADE` 的擁有者安全複合外鍵、附擁有者原則的強制 RLS，以及
  `apsor_app` 授權。既有檔案由 worker 回填補上。降級會移除該資料表；
- `a7d3c9e1f5b2` 建立私人的 `companion`、`companion_frame` 與
  `companion_preference` 資料表，每張都帶 `user_id`、僅限擁有者的強制 RLS 與
  `apsor_app` 授權。影格透過擁有者安全的複合外鍵參照其夥伴並一併串聯刪除；
  偏好資料列以 `user_id` 為鍵。降級會移除這三張資料表；
- `b8e4d2f6a1c3` 建立私人的 `companion_story`、
  `companion_lore_fragment` 與 `companion_bond` 資料表，帶僅限擁有者的強制 RLS
  與 `apsor_app` 授權：帳號依語言保存的夥伴人設與傳說副本、其片段，以及解鎖
  傳說層級的完成對話數。自訂夥伴的故事會隨夥伴一併串聯刪除。降級會移除這三張
  資料表。
- `c5f1a8d3e7b4` 為 `companion_preference` 新增 `size`（`compact`、
  `medium`、`full`，預設 `full`）與 `opacity_mode`（`opaque`、`translucent`、
  `auto`，預設 `opaque`），附檢查約束與伺服器預設值。RLS 與授權不變；降級會刪除
  這兩個欄位。
- `d2b6f4a8c1e9`為 `companion_preference` 新增可為 NULL 的
  `scale` 浮點數（0 為精簡、1 為完整），供直接在畫面上縮放使用，附範圍檢查。
  NULL 表示「使用 `size`」；只送 `scale` 時會推導出 `size`，只送 `size` 時會清除
  `scale`。RLS 與授權不變；降級會刪除這個欄位。
- `e4c8a2f6b0d3` 新增 `companion_lore_told`（每個帳號、夥伴與片段的
  `told_count`、`offered_at`、`last_told_at`、`source`）與
  `companion_bond.last_story_run`，用於故事時刻的節奏。僅限擁有者的 RLS。
- `f1a6c3e8b2d4` 新增全域、可由 root 編輯的夥伴世界資料表（預設角色、
  片段、設定詞條、世界觀文件與修訂、設定、提示詞模板、種子狀態），從
  `lore/` 植入，並以 `seed_hash`／`admin_modified`／`upstream_seed_hash`
  保留 root 的修改。所有人可讀、僅 root 可寫。
- `a2d7e4f9c3b5` 新增 `app.admin_scope = 'companion'` 政策（root 只能讀寫
  夥伴故事相關資料列，永遠碰不到檔案館內容）、由管理員管理的帳號資料表
  （帳號可讀不可寫）、新的羈絆欄位、`companion_lore_fragment.refs`，以及只能
  新增的 `companion_admin_access_log`。
- `b3e8f5a1d6c7` 新增 `companion_generated_story` 與 `companion_story_job`，
  供 worker 撰寫生活故事。
- `e7b2d5a9c4f1`（目前 head）新增 `chunk.embedding_failures` 與待嵌入的部分
  索引，並把 JSON `null` 嵌入轉為 SQL NULL，讓 worker 能在供應商或額度中斷後
  補上向量。

更早之前，`e7a1c4b9d2f6` 建立了單例 `agent_config` 資料表並植入資料列
`1`。整合測試套件會在可拋棄的 PostgreSQL 資料庫上執行移轉鏈，因此會
驗證角色、授權與 RLS 原則；Alembic 降級仍會另外針對開發資料庫驗證。

## 專案結構

Python 套件是 `apsor-archive-backend`（CLI 為 `apsor-archive`），用戶端
套件是 `apsor-archive-frontend`。

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
