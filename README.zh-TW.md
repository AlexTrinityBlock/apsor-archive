<div align="center">
  <img src="frontend/public/favicon.svg" alt="Apsor Archive" width="112" height="112">
</div>

<h1 align="center">Apsor Archive</h1>

<p align="center">
  為家庭或小型團隊打造的私人知識與記憶典藏，以本機為優先。
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

[English](README.md) · **繁體中文** · [简体中文](README.zh-CN.md)

## 目錄

- [重點特色](#重點特色)
- [技術堆疊](#技術堆疊)
- [快速開始](#快速開始)
  - [Docker Compose（一般）](#docker-compose一般)
  - [物件儲存（本機或 R2）](#物件儲存本機或-r2)
  - [在應用程式內設定供應商](#在應用程式內設定供應商)
  - [網路研究工具](#網路研究工具)
  - [常用提示詞](#常用提示詞)
  - [代理執行階段設定](#代理執行階段設定)
  - [資料匯入執行階段](#資料匯入執行階段)
  - [本機開發](#本機開發)
  - [Cloudflare Tunnel](#cloudflare-tunnel)
- [工具介面](#工具介面)
  - [資料夾工作區](#資料夾工作區)
  - [代理對話](#代理對話)
  - [儲存的問題](#儲存的問題)
  - [對話閱讀室](#對話閱讀室)
  - [對話工作區](#對話工作區)
  - [資源預覽](#資源預覽)
  - [帳號、角色與工作階段](#帳號角色與工作階段)
  - [產生的 API 用戶端與漂移](#產生的-api-用戶端與漂移)
  - [載入真實語料](#載入真實語料)
  - [長文件驗證](#長文件驗證)
- [檢索如何運作](#檢索如何運作)
  - [我需要嵌入模型的金鑰嗎](#我需要嵌入模型的金鑰嗎)
  - [什麼是帶符號雜湊嵌入器](#什麼是帶符號雜湊嵌入器)
- [資料模型](#資料模型)
- [開發檢查](#開發檢查)
- [專案結構](#專案結構)
- [安全性與隱私](#安全性與隱私)
- [授權](#授權)

這是一套以本機為優先的知識與記憶典藏，具備分支式檔案庫、線性記憶時間軸、
混合檢索（hybrid retrieval），以及有憑據的 AI 回答。每個帳號都有各自的私人
典藏；一個 root 帳號負責管理成員與共用的執行階段設定。

Apsor Archive 不是筆記清單。它是一個檢索介面，專為少量而刻意的工具呼叫而
設計：搜尋一個段落、讀取相鄰內容、沿路徑行走、取樣某個季節、壓製一則新
記憶，或追溯已被取代的記憶。每筆結果都帶著來源、分塊編號與時間。

> 狀態：v0.1.0 —— 檔案與記憶典藏、root 加上每位使用者各自的帳號、具備
> 資料庫後端執行階段限制的常駐 Pi 型代理、壓縮、平行工具、SSE 對話、
> 儲存問題的問答庫、可持久化的非同步資料匯入、專用的 PDF/DOCX/圖片/文字
> 預覽引擎、資料夾工作區，以及三面板對話工作區。

## 重點特色

- **檔案具有系譜。** 路徑是分支，不是覆寫。重新上傳檔案會長出新葉；先前的
  版本仍可作為歷史被定址。
- **資料匯入可持久化。** 上傳或直接輸入文字會立即傳回
  `file_ingest_job`，同時由有上限的 worker 解析、分塊、嵌入並發佈。佇列能
  承受重新啟動、回報進度，且絕不會露出只索引了一半的檔案。
- **檔案庫是資料夾工作區。** 資料夾是一等公民：就地建立、把檔案拖到資料夾
  卡片上即可上傳、把檔案卡片拖到另一個資料夾即可移動，想要獨立的第二筆
  紀錄時則使用明確的「複製」動作。
- **代理只有一個工作區。** 對話是含三個面板的工作台：可收合的對話抽屜、
  串流中的對話記錄，以及可拖曳且會保存分割比例的工具檢視器。沒有第二個
  輸入區，也沒有命令選擇區。
- **代理限制以資料庫為後端。** 模型脈絡視窗、回合預算、壓縮門檻、步驟與
  工具上限、平行寬度，以及結果預算，全都存放在單一經驗證的 `agent_config`
  資料列中，並套用至新的執行，無需重新啟動。脈絡視窗是模型中介資料，不是
  回合預算。
- **長討論串可以摺疊或清除。** 壓縮會寫入摘要邊界；清除會從空的活動脈絡
  開始。兩種情況下完整對話記錄仍可閱讀。
- **記憶是線性且可追溯的。** 新的信念可以取代舊的。舊記憶會離開搜尋介面，
  但仍可沿其鏈結閱讀。
- **搜尋是混合式的。** 以 CJK 雙字組與拉丁詞元進行的 BM25，與向量召回
  並行。結果會去重並融合，同時記錄原因。
- **時間取樣忠實呈現。** 時間軸每種事件種類最多傳回五個錨點，並精確回報
  略過了多少事件。
- **AI 回答有憑據。** DeepSeek 收到的是檢索到的段落，不是整個檔案庫，且
  每項主張都必須附上引用。沒有金鑰時，代理回合會封閉式失敗。
- **問題的生命超越對話。** 可以在還沒有答案時先儲存問題，之後再提問，並把
  答案、引用、執行狀態與對話連結留在同一資料列上。編輯問題會清除過期
  答案，而不是在畫面上留下彼此不符的配對。
- **圖片存在於檔案庫中。** 圖片是普通的檔案紀錄，帶有原始位元組、路徑與
  分塊。支援視覺的對話供應商會加上 OCR 與圖說中介資料；沒有這類供應商
  時，由檔名衍生的圖說仍讓本機上傳的內容可被搜尋。沒有另外的圖片索引。
- **文件會選擇自己的擷取器。** PDF 先嘗試文字，掃描頁面則退回視覺處理。
  DOCX、TXT、JSON、CSV 與日誌使用文字，並搭配 AI 結構化中介資料；圖片
  使用視覺處理或檔名備援。
- **介面說三種語言。** 英文、繁體中文與簡體中文可在設定頁切換。選擇會依
  瀏覽器儲存，套用至整個介面，但絕不套用至典藏內容。
- **典藏是私人、多帳號且以本機為優先的。** 一個 root 帳號管理帳號與全域
  執行階段設定；其他每個帳號都獲得一份私人典藏，涵蓋檔案、資料夾、分塊、
  記憶、摘要、對話、項目、執行、核准、儲存的問題、提示詞與個人檔案卡片。
  PostgreSQL 資料列級安全性在每張私人資料表上強制執行擁有權，因此即使
  查詢少了篩選條件，也無法揭露他人的典藏。密碼使用 Argon2，工作階段使用
  HttpOnly cookie。請在自己的機器上執行；只有在你自己具備存取控制時，才
  將它放在 Cloudflare Tunnel 之後。
- **原始位元組可以存放在 Cloudflare R2。** `APSOR_STORAGE_BACKEND=local|r2`
  決定新原始檔的寫入位置。讀取時遵循每筆資料列記錄的後端，因此分階段
  移轉期間可以服務混合的典藏。R2 儲存桶是私人的，應用程式絕不發出預先
  簽署或公開 URL。

## 技術堆疊

| 層次 | 選擇 |
|---|---|
| API | Python 3.13、FastAPI、SQLAlchemy 2 async、Alembic、psycopg 3 |
| 儲存 | PostgreSQL 17（`pg_trgm` 用於路徑模糊搜尋）；原始位元組位於本機磁碟或私人的 Cloudflare R2 |
| 快取 | Valkey／相容於 Redis，附記憶體內備援 |
| 檢索 | CJK 雙字組 + 拉丁詞元 n-gram、BM25、帶符號雜湊向量、RRF |
| AI | DeepSeek `deepseek-flash`（OpenAI 相容的對話完成） |
| 前端 | React 19、TypeScript、Vite、React Router、React Query、Orval |
| 部署 | Docker Compose、可選的 Cloudflare Tunnel，或使用 `uv` 的裸機部署 |

## 快速開始

### Docker Compose（一般）

```bash
mkdir -p data
sudo chown -R 10001:10001 data
# The production Compose default is R2; local disk is the simplest first run.
APSOR_STORAGE_BACKEND=local docker compose up --build
```

> 注意：`./data` 會綁定掛載到容器中，且容器程序以 uid `10001` 執行。請在
> 第一次開機前建立目錄並修正其擁有者，否則上傳與原始位元組寫入都會失敗。
> 若主機使用者已經是 uid `10001`，可以略過 `sudo chown`。

開啟 <http://127.0.0.1:8000>。第一次造訪時會要求你建立 root 帳號。root 接著
可以從 **帳號** 建立一般帳號；每個新帳號會收到一組一次性臨時密碼，並且必須
在第一次登入時變更。PostgreSQL 使用具名磁碟區；本機的原始位元組與產生的
祕密金鑰位於主機的 `./data` 目錄下。正式環境的 Compose 檔案預設為
`APSOR_STORAGE_BACKEND=r2`；其所需憑證請見
[物件儲存](#物件儲存本機或-r2)，或者為自成一體的主機保留本機儲存。

`postgres-data` 磁碟區固定使用明確的實體名稱：`docker-compose.yml` 為
`apsor-archive_postgres-data`，`docker-compose.dev.yml` 為
`apsor-archive-dev_postgres-data`，因此重新命名 Compose 專案不會讓資料庫成為
孤兒。在此次更名之前建立的堆疊使用了不同的實體磁碟區名稱，所以請在啟動前
將該磁碟區的內容複製到新的磁碟區（或在本機 Compose 檔案中保留舊名稱）。
否則 PostgreSQL 會初始化一個空資料庫。

API 映像檔會複製已提交的 `frontend/dist`；它不會執行前端建置。變更前端
程式碼後，請先執行 `cd frontend && bun run build`，再執行
`docker compose up --build`。

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
中。`644` 權限是必要的，因為 API 容器以非 root 使用者執行。金鑰已列入
gitignore，且 API 永遠不會傳回它。
沒有金鑰時，摘要會退回確定性的抽取式形式，圖片上傳會使用檔名圖說，代理
訊息則傳回 `503 agent_not_configured`。

### 物件儲存（本機或 R2）

`APSOR_STORAGE_BACKEND` 決定新原始位元組的預設寫入位置：

- `local` 寫入 `APSOR_DATA_DIR` 之下，是開發與測試的預設值。
- `r2` 寫入私人的 Cloudflare R2 儲存桶。兩個正式環境的 Compose 檔案都預設
  為 `r2`；第一次開機或回復時請設定 `APSOR_STORAGE_BACKEND=local`。

非祕密的 R2 值為 `APSOR_R2_ENDPOINT_URL`、`APSOR_R2_BUCKET`（部署中為
`apsor-archive`）、`APSOR_R2_REGION`（`auto`）與 `APSOR_R2_PREFIX`。帳號
端點沒有預設值：在以 `r2` 後端執行之前，請將
`APSOR_R2_ENDPOINT_URL=https://<account-id>.r2.cloudflarestorage.com` 放入
Compose 檔案旁、已列入 gitignore 的 `.env` 檔案，或先匯出該變數。憑證位於
已列入 gitignore 的 `.secrets/r2.env`，Compose 會以唯讀方式掛載，並由應用
程式自行讀取，因此它們永遠不會成為容器環境變數：

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

該檔案必須能被容器 uid `10001` 讀取（權限 `640` 且群組為 `10001`，或在
單一使用者的主機上使用 `644`）。儲存桶維持私人：沒有預先簽署 URL、沒有
公開的儲存桶存取，且 `files/` 沒有生命週期到期設定。`data/.secret_key` 是
Fernet 主金鑰，只留在本機；請與 PostgreSQL 分開備份。

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

### 在應用程式內設定供應商

設定頁是設定供應商的標準方式，且只有 root 帳號能編輯全域登錄。它會寫入
四張各自獨立的能力資料表，因此一種能力永遠不會覆寫另一種：

- **對話** —— `chat_provider_config`：DeepSeek 或任何 OpenAI 相容的對話
  端點。允許保存多個資料列；恰有一個處於使用中。
- **嵌入** —— `embedding_provider_config`：離線的 `hashing`、`openai` 或
  `openai-compatible`。允許保存多個資料列；恰有一個處於使用中。
- **網路搜尋** —— `web_search_provider_config`：目前為 Tavily，並保留
  供應商轉接器的擴充接縫，以供未來的搜尋 API 使用。允許保存多個資料列；
  恰有一個處於使用中。
- **網路取得** —— `web_fetch_provider_config`：目前為 Tavily `extract`。
  網路搜尋與網路取得刻意分成不同資料列，因此它們可以使用不同的供應商或
  不同的憑證。

每張資料表都對 `is_active` 設有部分唯一索引；PostgreSQL 會強制每種能力
最多只有一個使用中的資料列。刪除資料列不會重複使用其身分 ID。供應商
資料列屬於全域部署設定：只有 root 帳號可以列出、編輯、測試或刪除它們，
一般使用者永遠不會收到供應商祕密或全域執行階段設定。API 永遠不會傳回
明文金鑰：瀏覽器只會收到例如 `...14f8` 的提示。`APSOR_SECRET_KEY` 提供
Fernet 主金鑰。若未設定，會在 `data/.secret_key`（Docker 中為
`/data/.secret_key`）建立 `0600` 權限的金鑰檔案，因此加密值能承受重新
啟動。`APSOR_TAVILY_API_KEY` 是兩種網路能力可選的環境備援。

優先順序為：**使用中的資料庫資料列 → 環境 → 內建預設值**。設定頁會標示
每個供應商的來源。變更嵌入模型不會重寫現有向量；`reindex_required` 會
提出警告。請執行 **重新嵌入檔案庫**（或
`POST /api/v1/settings/providers/embedding/reindex`）來更新目前的分塊。
向量搜尋會略過維度與目前嵌入器不符的分塊。

供應商登錄 API：

| 方法 | 路徑 | 用途 |
|---|---|---|
| `GET` | `/api/v1/settings/providers` | 四個能力群組、遮蔽提示、使用中的資料列、重新索引建議 |
| `POST` | `/api/v1/settings/providers/{capability}` | 建立一個儲存的供應商；可選擇將其啟用 |
| `PUT` | `/api/v1/settings/providers/{capability}/{provider_id}` | 取代一個儲存的供應商 |
| `DELETE` | `/api/v1/settings/providers/{capability}/{provider_id}` | 刪除一個儲存的供應商 |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/activate` | 使其成為該能力唯一使用中的資料列 |
| `POST` | `/api/v1/settings/providers/{capability}/deactivate` | 清除使用中的資料列，並退回環境／預設值 |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/test` | 送出一個小型供應商請求並測量延遲 |
| `POST` | `/api/v1/settings/providers/embedding/reindex` | 以使用中的供應商重新嵌入每個目前的分塊 |

`{capability}` 是 `chat`、`embedding`、`web_search` 或 `web_fetch` 之一。
登錄回應會在 `providers` 快取範圍下快取 30 秒；每次供應商寫入都會更新該
範圍。

### 網路研究工具

代理有兩個唯讀工具可用於外部研究：

| 工具 | 功能 |
|---|---|
| `web_search` | 以使用中的 `web_search` 供應商搜尋公開網路；傳回標題、URL、分數與有上限的摘錄。 |
| `web_fetch` | 以使用中的 `web_fetch` 供應商取得一個公開的 `http(s)` URL，並傳回一個由伺服器定義的 Markdown 頁面。 |

Tavily 是第一個轉接器（`/search` 與 `/extract`）。供應商接縫是一個協定，
因此可以新增另一個搜尋或取得 API，而不需變更工具層。搜尋結果會在
`providers` 快取範圍下快取 15 分鐘；供應商寫入會使其失效。`web_fetch`
會拒絕非 HTTP(S)、URL 中含憑證、`localhost`/`.local`/`.internal`，以及
私有或特殊用途的 IP 字面值。

`web_fetch` 會為每個 URL 快取完整的擷取文件一次，為期一小時，因此翻頁
永遠不會再次呼叫供應商。其面對模型的引數只有 `url` 與 `page`（從 1 開始，
預設為 1）。伺服器會將每個來源行硬性折行於 800 字元，並將整行打包成最多
12,000 字元的頁面（或在較小時使用設定的 `web_fetch_max_chars`，且絕不低於
801），因此頁面永遠不會超出其預算，且一定至少包含一行。沒有行號需要計算，
也沒有位移需要計算：先呼叫 `page=1`，再呼叫 `page=2`，依此類推直到
`has_more=false`。每筆結果都會回報 `page`/`total_pages`、`page_chars`、
`total_chars`、`has_more`、`next_page` 與 `source_truncated`，且本文結尾
會有一段純文字頁尾，例如：

```text
[web_fetch: page 1/2. More content: call web_fetch again with page=2.]
```

每當 `has_more=true` 時，`next_page` 都是精確的。串接每一頁會恰好涵蓋
快取文件一次，沒有缺口或重疊。正規化後的文件全長上限為 2,000,000 字元；
超過時會被截斷並設為 `source_truncated=true`，因此最後一頁的頁尾會說明
來源已被截斷。兩個工具都會傳回帶有 `provider`、`retrieved_at`、`cached`
與 `truncated` 的 XML，且代理會被指示要引用 URL 與取得時間。

對話在建立時會凍結其工具快照，因此較舊的對話會保留先前的 `web_fetch`
結構描述。先前的 `offset`、`limit` 與 `max_chars` 引數仍會被接受，但會
從面對模型的結構描述中隱藏；它們存在只是為了讓凍結在 `archive-tools-v4`/
`v5` 的對話能繼續通過驗證。頁面模式會忽略 `max_chars` 與 `limit`，而
舊版的 `offset` 只會選出包含該行的頁面。

摘要搜尋結果與時間軸摘要事件會明確標記為壓縮檢視：

```xml
<source kind="summary" id="12" view="compressed" memory_count="37" ...>
  <compressed_view coverage_start="..." coverage_end="..." source_memory_count="37">
    This is a compressed summary of 37 original memories, not the complete original content.
  </compressed_view>
  ...
</source>
```

代理會在工具結果本身看到 `view="compressed"`、涵蓋範圍視窗與原始記憶
數量，因此不會把摘要當成完整對話記錄。

### 常用提示詞

`/settings` 上的 **常用提示詞** 面板會編輯空白 `/chat` 頁面上顯示的捷徑。
該清單對登入的帳號是私人的：每個資料列有標題、提示詞文字與 `sort_order`；
每個帳號上限為 20 個資料列，依 `sort_order` 再依 `id` 排序，並在該帳號的
`prompts` 快取範圍下快取 60 秒。點擊捷徑會以完整的提示詞文字填入輸入區；
它不會送出訊息。API 為
`GET/POST/PUT/DELETE /api/v1/settings/frequent-prompts`。

### 代理執行階段設定

`/settings` 上的 **代理執行階段** 面板（僅限 root）會編輯單例的
`agent_config` 資料列（`id=1`）。供應商與模型選擇仍留在上方的 AI 設定中，
因此哪個模型負責回答仍然只有單一事實來源。全部十三個執行階段值都存放在
PostgreSQL 中，套用至新的執行且無需重新啟動，並由每個帳號共用。

| 方法 | 路徑 | 用途 |
|---|---|---|
| `GET` | `/api/v1/agent/settings` | 生效設定、預設值、來源、`updated_at` |
| `PUT` | `/api/v1/agent/settings` | 完整取代；十三個欄位皆為必填 |
| `POST` | `/api/v1/agent/settings/reset` | 保存並傳回內建預設值 |

產生的操作為 `getAgentSettings`、`updateAgentSettings` 與
`resetAgentSettings`。

讀取結構為 `{config, defaults, source, updated_at}`，其中 `source` 在資料列
已儲存時為 `database`，而在 API 必須從預設值建立或修復該資料列時為
`default`。`PUT` 要求完整快照：省略的欄位與額外的欄位都會被拒絕。

| 欄位 | 預設 | 範圍 |
|---|---|---|
| `max_total_tokens` | 100,000 | 8,000–200,000 |
| `compaction_threshold_tokens` | 75,000（約 75%） | 1,000–200,000 |
| `context_window_tokens` | 1,000,000 | 8,000–2,000,000；模型中介資料，不是回合預算 |
| `max_steps` | 24 | 1–32 |
| `max_tool_calls_per_turn` | 20 | 1–24 |
| `max_parallel_tools` | 6 | 1–24 |
| `max_tool_result_chars` | 100,000 | 1,000–200,000 |
| `max_page_context_chars` | 6,000 | 500–50,000 |
| `max_compaction_summary_chars` | 6,000 | 1,000–20,000 |
| `max_compaction_last_user_chars` | 4,000 | 500–10,000 |
| `auto_compaction_enabled` | `true` | 布林值 |
| `parallel_tools_enabled` | `true` | 布林值 |
| `save_memory_requires_approval` | `true` | 布林值；`save_memory` 需要人工核准 |

Pydantic 與對應的 PostgreSQL 檢查條件約束會強制執行範圍與兩項跨欄位規則：
壓縮門檻必須低於總權杖預算，且平行寬度不得超過每回合的工具呼叫數。脈絡
視窗與兩者無關；變更它永遠不會提高回合預算。應用程式的全域驗證封套會將
請求驗證失敗對應為 `400 invalid_request`，而非 422。

請求會在一次短暫的資料庫工作階段中載入一個不可變的執行階段快照。進行中
的 SSE 執行會保留它啟動時的快照；之後的執行則使用已變更的設定。後端契約
描述於 `backend/README.md`。

### 資料匯入執行階段

同步的 `POST /api/v1/files` 與 `POST /api/v1/files/text` 端點仍然存在，但
UI 可以改為將工作排入佇列。非同步路由會儲存酬載並傳回 `202` 與
`IngestJobSchema`：

| 方法 | 路徑 | 操作 |
|---|---|---|
| `POST` | `/api/v1/files/async` | `uploadFileAsync` |
| `POST` | `/api/v1/files/text/async` | `createTextFileAsync` |
| `GET` | `/api/v1/files/ingest-jobs?limit=&offset=` | `listIngestJobs` |
| `GET` | `/api/v1/files/ingest-jobs/{id}` | `getIngestJob` |
| `POST` | `/api/v1/files/ingest-jobs/{id}/retry` | `retryIngestJob` |

工作會依序經過 `queued(0)`、`parsing(5)`、`chunking(15–20)`、
`embedding(25–90)`、`summarizing(95)` 與 `ready(100)`，或以 `failed` 結束。
`progress_pct`、`chunks_total` 與 `chunks_embedded` 是可持久化的，因此重新
載入的頁面可以接續相同的顯示。暫存的檔案與分塊資料列只會在工作就緒時
發佈；失敗的工作會保留其錯誤，但不露出任何部分完成的目前檔案。

一個 worker 程序在閒置時每秒輪詢資料庫，並以
`SELECT ... FOR UPDATE SKIP LOCKED` 認領排入佇列的資料列。它會執行兩個
擷取執行緒與最多兩個進行中的工作，全域非同步嵌入並行度為六，並批次更新
進度。過期的工作會在崩潰後重新排入佇列，嵌入重試則有次數上限。API 生命
週期會為本機使用啟動一個 worker；正式環境請執行專用程序：

```bash
cd backend
uv run apsor-archive worker
# or
uv run python -m app.worker
# process at most one job, then exit
uv run python -m app.worker --once
```

標準與 Cloudflare Compose 堆疊會將它作為專用的 `worker` 服務執行，並在
API 上設定 `APSOR_INGEST_WORKER_ENABLED=false`，因此恰好只有一個程序擁有
佇列。

`/settings` 上的 **資料匯入執行階段** 面板（僅限 root）會編輯單例的
`ingest_config` 資料列。它是完整取代，不是修補，且讀取本文會帶有
`{config, defaults, source, updated_at}` 與「資料庫／預設」標籤。worker 可以
跨帳號認領工作，但每個解析、分塊、嵌入與發佈步驟都會在工作擁有者的
資料列級安全性脈絡中執行。

| 方法 | 路徑 | 操作 |
|---|---|---|
| `GET` | `/api/v1/settings/ingest` | `getIngestSettings` |
| `PUT` | `/api/v1/settings/ingest` | `updateIngestSettings` |
| `POST` | `/api/v1/settings/ingest/reset` | `resetIngestSettings` |

| 欄位 | 預設 | 範圍 |
|---|---|---|
| `poll_seconds` | 1.0 | 0.25–30 |
| `extract_workers` | 2 | 1–8 |
| `max_inflight_jobs` | 2 | 1–4 |
| `embedding_concurrency` | 6 | 1–32 |
| `chunk_target_chars` | 4,000 | 1,000–20,000 |
| `chunk_overlap_chars` | 500 | 0–5,000；須低於目標值 |

worker 會在每次迴圈與每個工作讀取最新的資料庫快照，因此已儲存的 worker
變更無需重新啟動即可套用；已在執行中的工作則保留其快照。環境值會為全新
安裝提供初始值，並持續作為備援。變更分塊大小只會影響未來的匯入。後端
契約描述於 `backend/README.md`。

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

`./start.sh` 是最短的裸機路徑：若 Docker 可用，它會啟動開發資料庫／快取、
載入 `.secrets/deepseek.env`、同步後端，並在 <http://127.0.0.1:8000> 提供
API 與已提交的用戶端。

在 Windows 上，`./start.sh` 需要 bash shell。`./run-local.ps1` 是 PowerShell
的對等版本：若 Docker 可用，它會啟動開發資料庫／快取、同步後端，並提供
相同的 URL。應用程式會自行讀取 `.secrets/`，因此指令碼不會匯出那些值。
它也會強制使用 `SelectorEventLoop`，因為 psycopg 的非同步模式會拒絕
uvicorn 在 Windows 上預設選用的 `ProactorEventLoop`。

```powershell
.\run-local.ps1            # http://127.0.0.1:8000
.\run-local.ps1 -Port 8080
```

### Cloudflare Tunnel

這是 **Tunnel** 部署變體。未來純 Cloudflare Serverless 部署應使用自己的
compose 檔案；tunnel 堆疊留在 `docker-compose.cloudflare-tunnel.yml`。它
不發佈任何主機連接埠。`cloudflared` 連線至非 root 的 Caddy 反向代理，
再由其轉送至 API。

```bash
mkdir -p secrets
# Write the tunnel token; no trailing newline.
printf '%s' 'your-tunnel-token' > secrets/cf_token.txt
chmod 644 secrets/cf_token.txt
export APSOR_PUBLIC_HOST=archive.example.com
docker compose -f docker-compose.cloudflare-tunnel.yml up -d --build
```

將 `archive.example.com` 的 tunnel ingress 指向 `http://caddy:80`。權杖
檔案已列入 gitignore。Caddy 只服務 `APSOR_PUBLIC_HOST` 指定的主機，並對
其他所有主機回應 `404`，因此請勿在 tunnel ingress 加入第二個公開主機名。
權限說明請見
`secrets/README.md`，完整的英文部署、備份、安全性與疑難排解指南請見
[`docs/cloudflare-tunnel.md`](docs/cloudflare-tunnel.md)。

## 工具介面

典藏對外提供六個小型 HTTP 工具。每個 JSON 端點都對應代理可呼叫的一項檢索
或記憶操作；每個酬載都刻意小到足以讓 LLM 依序使用。

| 工具 | 端點 | 傳回內容 |
|---|---|---|
| `search_knowledge` | `GET /api/v1/search?query=&result_number=2` | 依來源種類分別取 BM25 + 向量的前幾名結果，以 RRF 融合並去重 |
| `read_file` | `GET /api/v1/files/{file_id}/chunks/{chunk}?chunk_range=1` | 從 1 開始算起的分塊視窗 |
| `read_timeline` | `GET /api/v1/timeline?year=&month=&day=&day_range=1` | 每種事件種類最多五個取樣事件、密度與略過數量 |
| `read_path` | `GET /api/v1/paths?path=/history&path_depth=1&fuzzy_search=` | 目錄與檔案，或模糊路徑比對 |
| `save_memory` | `POST /api/v1/memories` | 一則帶有自動產生標題的新記憶、它所取代的已汰除記憶，以及任何新摘要；省略 `content` 即可汰除 `supersedes` ID 而不提供替代內容 |
| `read_memory` | `GET /api/v1/memories/{memory_id}?memory_range=1&trace_history=true` | 目標、相鄰項目、取代者、後繼者與鏈結 |

常駐典藏代理對模型提供九個工具：上述六個加上 `present_resource`、
`web_search` 與 `web_fetch`。HTTP 範例使用明確參數；HTTP 伺服器預設值為
`result_number=2`、`chunk_range=1`、`day_range=1`、`path_depth=1` 與
`memory_range=0`。文字會以約 4,000 字元、500 字元重疊的方式分塊；現有
檔案會保留其原始分塊邊界，直到重新匯入為止。代理的工具結構描述會選擇
自己的預設值，例如 `result_number=8` 與 `day_range=7`。對於外部的 LLM
呼叫者，另有一個 `/api/v1/tools/*`  façade 會將相同的服務呈現為精簡的
XML；常駐代理則透過自己的登錄直接呼叫這些服務。

`present_resource` 會傳回例如 `/viewer/file/{id}?chunk={n}` 或
`/viewer/memory/{id}` 的資源 URL，且永遠不會取得該資源。用戶端會將檔案
連結重新導向至檔案庫的預覽彈出視窗，並將記憶連結導向記憶閱讀器。

在對話檢視器中，`web_search` 會展開查詢、供應商、取得時間，以及每個帶有
可點擊 URL、摘錄與分數的結果；`web_fetch` 會展開來源中介資料與取得的
本文。網路結果 URL 與取得的內容都有複製動作。記憶引用會以
`Memory: <generated title>` 的形式呈現給人看，而模型與工具提示則保留穩定
的 `[memory:id]`。記憶文字、每個檔案分塊與對話記錄也都有單鍵複製動作。

每筆記憶資料列都會儲存一個簡短的自動產生 `title`。在儲存與編輯時，後端
會先向設定的對話供應商要求名稱，再進行單次插入或更新，因此本文與標題會
以原子方式儲存。若供應商無法使用，本文的前 80 個字元會成為備援標題。
對話會將每則記憶引用呈現為數字標籤加上該名稱；較舊的對話記錄會透過
`read_memory` 隨需解析缺少的名稱。

`save_memory` 有一種不含替代內容的汰除形式：省略 `content`，在
`supersedes` 中傳入現有 ID，並可選擇包含 `reason`。後端會將那些資料列
標記為已汰除、寫入 `deprecated_at`、將其搜尋分塊標記為非目前，且不寫入
任何新記憶。同一個呼叫若帶有 `content`，則保留原本的取代行為。

已保存的 `pi.tool-result` 項目也會帶有僅供 UI 使用的 `data`：供展開檢視器
使用、有大小上限的摘錄、維度、標籤與檢視器 URL。此酬載永遠不會進入供應商
訊息；模型仍然只看到 XML 工具結果。

`save_memory` 是寫入動作。`save_memory_requires_approval` 執行階段設定
（預設 `true`，可在 **設定 → 代理執行階段 → 工具執行** 中編輯）控制其
授權方式：

- **開啟（預設）：** 迴圈不會執行寫入。它會保存一筆可持久化的
  `agent_approval` 資料列、暫不附加工具結果、將執行移至 `waiting`，並
  發出 `approval_required`，附上大小有上限的預覽。僅汰除的呼叫會預覽目標 ID 與
  原因，而不是提議的本文。`POST
  /api/v1/agent/approvals/{approval_id}/approve` 是唯一會執行寫入的路徑；
  `.../reject` 會附加 `memory_rejected` 工具結果並在未寫入的情況下繼續。
  模型的 `user_confirmed` 引數在授權上會被忽略。
- **關閉：** 不會建立等待中的執行或核准資料列。後端會自行授權經驗證的
  寫入（工具登錄中的 `approved=True`），且呼叫會在同一個回合完成。模型
  提供的 `user_confirmed` 仍然永遠不會授權寫入。

重複或過期的處置會傳回 `409 agent_approval_not_pending`，而已封存或已
刪除的對話則會封閉式失敗。停用此設定不會核准或取消已存在的核准；它們
仍是明確的待處理資料列，其卡片也會繼續呈現。展開的檢視器在寫入後仍會
呈現產生的收據。

其他介面：`POST /api/v1/files`（多模態匯入）、`POST
/api/v1/files/text`、`DELETE /api/v1/files/{file_id}`、`GET /api/v1/paths`、
`GET /api/v1/memories`、`POST /api/v1/memories`、
`PATCH /api/v1/memories/{memory_id}`（編輯文字；標題會重新產生）、
`POST /api/v1/memories/{memory_id}/deprecate`（以可選的 `reason` 直接
汰除）、`POST /api/v1/summaries`、`GET /api/v1/stats`、
`GET /api/v1/health` 與 `GET /api/v1/ai/status`。

### 資料夾工作區

`/library` 是資料夾優先的工作區。麵包屑與資料夾側欄描述你所在的位置；主
區域會顯示目前路徑的資料夾卡片與檔案卡片。先前的表格仍以精簡清單檢視
提供，供密集瀏覽使用，也是窄螢幕上的備援版面。

- **新增資料夾** 會建立要求的資料夾與任何缺少的祖先資料夾。此操作是
  冪等的：重複執行會傳回相同的資料夾與 `201`。
- **拖放上傳** 接受從桌面拖放到資料夾卡片或目前資料夾介面的檔案。上傳
  使用與上傳對話框相同的匯入路徑、副檔名允許清單與伺服器限制：每個上傳
  檔案 10 MB，以及 `.md`、`.markdown`、`.txt`、`.csv`、`.json`、`.log`、
  `.pdf`、`.docx`、`.jpg`、`.jpeg`、`.png` 或 `.webp`。對話框也支援
  2 MB 的純文字建立。拖放的檔案永遠不會被開啟或執行。
- **移動與複製** 是明確區分的。正常拖放到資料夾會移動檔案；拖放時按住
  Alt/Option 則會複製。觸控與鍵盤使用者會取得獨立的 **移動** 與
  **複製** 動作，而不是拖放。
- **移動** 會保留相同的檔案 ID、版本、分塊、嵌入與原始位元組。只有
  `raw_file_path` 與檔案名稱會改變，因此現有的搜尋、時間軸、引用與檢視器
  連結仍然有效。
- **複製** 會在版本 1 建立新的目前檔案 ID，若存在已儲存的原始檔則予以
  複製，重建分塊與嵌入，並複製 AI 摘要、標籤、文件類型與擷取方法。兩個
  檔案都會保持目前且可搜尋。
- 移動與複製都必須保留原始副檔名。目標若已被另一個資料夾或目前檔案
  佔用，會傳回 `409 tree_path_conflict`；無效路徑或變更副檔名會傳回
  `422 invalid_path`。

| 方法 | 路徑 | 本文 | 用途 |
|---|---|---|---|
| `POST` | `/api/v1/folders` | `{path}` | 建立資料夾與缺少的祖先資料夾；冪等 `201` |
| `POST` | `/api/v1/files/{file_id}/move` | `{path}` | 將一個目前檔案就地移動；`200` |
| `POST` | `/api/v1/files/{file_id}/copy` | `{path}` | 將一個目前檔案複製為新紀錄；`201` |

三個端點都要求已驗證的帳號，且只會操作該帳號的資料夾樹。當它們變更
資料夾或檔案索引時，會提升該帳號的典藏快取版本；另一個帳號中的路徑是
獨立且不衝突的樹。

### 代理對話

`/api/v1/agent` 是一個常駐、Pi 型的多回合典藏代理。「Pi 型」指的是 Pi
coding-agent harness 的持久化逐字稿模型：對話是一份由不可變項目組成的
追加式日誌，供應商脈絡會在最新的 reset 或壓縮邊界之後由該日誌重建，而不是
來自可變的聊天陣列。Apsor Archive 以 Python 與 PostgreSQL 實作此模型，不
執行 Pi 執行環境，也不依賴其套件。相關資料表如下：

- `agent_conversation` —— 對話記錄範圍、供應商／模型身分與中介資料。
- `agent_entry` —— 不可變的 `pi.user`、`pi.assistant`、`pi.tool-result`、
  `pi.page-context`、`pi.system`、`pi.reset`、`pi.compaction` 與
  `ui.notice` 項目。`model` 正是供應商酬載；`data` 僅供 UI／診斷使用。
- `agent_run` —— 單次提交的可持久化狀態（`request_id`、狀態、中止、最後
  項目、安全錯誤）。`agent_commit_seq` 會將同一交易中寫入的項目分組。
- `agent_approval` —— 針對需要確認的工具呼叫，保存一筆可持久化的
  待處理／已核准／已拒絕／已過期的人工決定，包含經驗證的引數、安全預覽，
  以及用來恢復等待中執行的迴圈快照。
- `agent_config` —— 單例執行階段設定（`id=1`），保存經驗證的權杖、步驟、
  工具、頁面脈絡與壓縮限制。

第一個項目是凍結的 `pi.system` 提示詞與工具快照。脈絡建構器會以確定性
方式重播項目：它會遵循 `head_entry_id` 與 `edits`、保留系統項目、將工具
結果直接移到其助理呼叫之後、合成缺少的結果、丟棄孤兒結果，並排除失敗的
助理嘗試。工具呼叫會經驗證並以結構化結果傳回；工具失敗永遠不會變成
HTTP 500。

| 方法 | 路徑 | 用途 |
|---|---|---|
| `POST` | `/api/v1/agent/conversations` | 建立對話及其系統項目 |
| `GET` | `/api/v1/agent/conversations` | 列出使用中／已封存的對話，最新活動優先 |
| `GET` | `/api/v1/agent/conversations/{conversation_id}` | 中介資料加上第一頁項目 |
| `GET` | `/api/v1/agent/conversations/{conversation_id}/entries?after_id=&limit=` | 遞增的項目分頁 |
| `PATCH` | `/api/v1/agent/conversations/{conversation_id}` | 重新命名、封存或還原 |
| `DELETE` | `/api/v1/agent/conversations/{conversation_id}` | 軟刪除；項目保留供稽核 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/compact` | 附加手動壓縮邊界 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/clear` | 附加重設邊界；對話記錄會保留 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/fork` | 將包含截止點在內的項目複製到新討論串 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/messages` | 附加使用者項目並執行迴圈 |
| `POST` | `/api/v1/agent/conversations/{conversation_id}/retry` | 重試最近一次失敗／取消的執行 |
| `GET` | `/api/v1/agent/conversations/{conversation_id}/approvals?status=` | 可持久化的核准，最舊優先（預設 `pending`） |
| `POST` | `/api/v1/agent/approvals/{approval_id}/approve` | 執行一次、附加工具結果、繼續 |
| `POST` | `/api/v1/agent/approvals/{approval_id}/reject` | 附加 `memory_rejected`，未寫入即繼續 |
| `GET` | `/api/v1/agent/tools` | 目前工具目錄加上提示詞／工具版本 |
| `GET` | `/api/v1/agent/settings/system-prompt` | 列出每個系統提示詞區段 |
| `POST` | `/api/v1/agent/settings/system-prompt` | 建立一個區段（`201`） |
| `PUT` | `/api/v1/agent/settings/system-prompt/order` | 重新排序每個區段 |
| `PUT` | `/api/v1/agent/settings/system-prompt/{section_id}` | 取代一個區段 |
| `DELETE` | `/api/v1/agent/settings/system-prompt/{section_id}` | 刪除一個區段（`204`） |
| `POST` | `/api/v1/agent/settings/system-prompt/reset` | 以四個初始預設區段取代每個區段 |

`POST /api/v1/agent/conversations/{conversation_id}/messages` 接受
`{content, request_id?, page_context?, client_timezone?,
client_utc_offset_minutes?}`，而 `.../retry` 接受 `{request_id?}`。兩者
預設都會串流 `text/event-stream`。用戶端時區會與伺服器呈現的
`<current_time>` 區塊一起儲存在每個使用者項目上；該區塊會恰好附加在訊息
文字之後一次。排序後的系統提示詞區段會在建立對話時寫入，並凍結到該
討論串中。四個預設值會以一般資料列初始植入；設定頁讓 root 帳號能為整個
部署編輯、刪除或重新排序每一個資料列。事件名稱為 `run_start`、
`message_start`、`message_delta`、`message_end`、`tool_start`、
`tool_end`、`approval_required`、`run_end` 與 `error`。`run_start` 會
回報 `page_context_entry_id`（或 `null`）、`page_context_attached` 與
`resumed`，讓用戶端能標示是否寫入了新快照，以及串流是否接續一筆可持久化
的等待中執行。`tool_start` 與 `tool_end` 也會帶有助理呼叫批次的
`parallel`、`batch_size` 與 `parallel_index`。`tool_end` 帶有已保存的
工具結果 `data` 酬載，加上 `duration_ms` 與 `error_code`，因此檢視器
可以在對話記錄重新取得完成前先呈現預覽。`message_start` 的
`entry_id=null`，因為助理項目只會在 `message_end` 時保存；增量僅供傳輸。
若想要取得完成的回合，請改送 `Accept: application/json`。SSE 回應會設定
`Cache-Control: no-cache, no-transform` 與 `X-Accel-Buffering: no`，
且 Starlette 的 GZip 中介軟體會排除 `text/event-stream`。

每個對話一次只允許一筆使用中的執行。預設值允許 24 個模型步驟、每個
使用者回合 20 次工具呼叫、6 個平行工具、每回合 100,000 個權杖（跨模型步驟
累計）、自動壓縮前 75,000 個權杖，以及每個工具 100,000 個結果字元。
另有 1,000,000 權杖的模型脈絡視窗記錄供應商容量；它是中介資料，不會提高
回合預算或改變壓縮。每個結果都會依該單一結果上限獨立裁切，並附上可見的
`[truncated]` 標記；沒有整回合的結果預算，也沒有第二次摘要呼叫。
100,000 字元的上限大約涵蓋二十五個 4,000 字元的分塊。這些是執行階段
設定，不是程式碼常數；請見上方的 **代理執行階段設定**。符合條件的工具
呼叫會一起開始，並在啟用平行工具時透過 `asyncio.gather` 執行。結果保存
與 `tool_end` 的順序遵循助理呼叫順序，而不是完成順序。停用平行工具時，
執行會依序進行，且事件會回報 `parallel=false`。

失敗或取消的執行可以重試，而不會重複使用者項目。當最新項目是失敗／取消
的助理回答、結尾的硬性上限工具結果（`step_limit`、`token_limit`、
`tool_call_limit` 或 `tool_result_budget_exhausted`），或最後一次串流在
記錄助理項目之前就失敗時，對話工作台與停駐的代理都會顯示「重試」動作。
重試會為同一個使用者項目啟動新的執行；UI 不會附加第二則訊息，並在串流
進行中停用該動作。若對話記錄仍然太長，重試可能會再次觸及相同的脈絡或
權杖預算。當最近一次執行已完成或並非失敗／取消時，端點會傳回
`409 agent_run_not_retryable`；UI 會在該錯誤後重新取得對話記錄，讓過期的
「重試」動作消失。

#### 對 `save_memory` 的人工核准

當 `save_memory_requires_approval=true`（預設值）時，有效的確認呼叫永遠
不會從模型迴圈寫入。它會保存 `agent_approval`，包含對話、執行、工具
呼叫 ID、經驗證的引數、安全預覽與恢復快照；同一批次中的安全呼叫仍會
執行，其結果也會被附加。執行會變成 `waiting`，SSE 串流以
`approval_required` 加上 `run_end {status: "waiting"}` 結束，且助理工具
呼叫會留在對話記錄中。一個含有多個確認呼叫的批次會為每個呼叫建立一筆
核准；處置必須依核准 ID 順序進行，且迴圈會在最末一筆待處理資料列處置
完畢後繼續。

關閉此設定時，經驗證的呼叫會立即以後端授權（`approved=True`）執行，
不會建立 `agent_approval` 資料列，執行也會正常完成。模型的
`user_confirmed` 引數在兩種模式下都永遠不會授權寫入。關閉此設定不會處置
已存在的核准；其卡片仍會保留，且需要明確的決定。

| 方法 | 路徑 | 用途 |
|---|---|---|
| `GET` | `/api/v1/agent/conversations/{id}/approvals?status=pending` | 待處理的核准，最舊優先 |
| `POST` | `/api/v1/agent/approvals/{approval_id}/approve` | 執行一次、附加結果、繼續 |
| `POST` | `/api/v1/agent/approvals/{approval_id}/reject` | 附加 `memory_rejected`，未寫入即繼續 |

兩個處置端點都接受 `Accept: application/json`，或將恢復的回合以 SSE
串流。它們會以 `run_start {resumed: true}` 開始，接著是處置結果的
`tool_end`；若仍有另一筆核准，會以 `approval_required` 與
`run_end {status: "waiting"}` 結束，否則一般迴圈會繼續。在資料列已處置、
已過期或已成為孤兒之後才核准，會傳回 `409 agent_approval_not_pending`；
已封存的對話則傳回 `409 agent_conversation_archived`。

API 重新啟動時，過期的 `running` 執行會以 `interrupted` 失敗。帶有有效
待處理核准的 `waiting` 執行會存活，並仍可從核准端點看見。沒有有效待處理
核准的等待中執行會以 `approval_orphaned` 封閉式失敗。暫停是僅附加的：
只有 `agent_run`/`agent_approval` 的操作欄位會改變，真正的工具結果會在
決定到達時附加。

對話詳細資料會傳回第一頁項目，UI 則以 **載入更多項目** 載入後續頁面。
它也會傳回 `last_page_context_key`，該值讀自項目記錄而非瀏覽器儲存，因此
重新載入的對話仍知道上次附加的是哪個頁面快照。

#### 壓縮與清除

當 `auto_compaction_enabled` 為 true，且在新使用者回合之前估計的活動脈絡
超過 `compaction_threshold_tokens` 時，該回合會先附加一個 `pi.compaction`
項目：

- 該項目會將 `head_entry_id` 設為自己的 ID，因此較舊的項目維持不可變，
  但會落在新的活動脈絡之外。
- 其供應商訊息以 `<compaction>` 開頭，並帶有 `<last_user_input>`（壓縮前
  的最後使用者輸入）與 `<summary>`。
- 同一筆交易會依序寫入壓縮 → 頁面脈絡（當頁面重新附加時）→ 使用者，
  因此模型會在新的請求之前看到摘要。

這會開始新的 KV 快取系譜。系統提示詞與工具快照維持凍結，舊的對話記錄
仍可在 `/chat` 與浮動面板中閱讀。

`POST .../compact` 會從目前的活動脈絡手動附加相同的邊界。
`POST .../clear` 會附加 `pi.reset`，其 `head_entry_id` 指向自己，且沒有
供應商訊息；對話記錄會保留，但下一個回合會從空的活動脈絡開始。它們的
操作 ID 為 `compactAgentConversation` 與 `clearAgentConversation`。兩者
都會在執行進行中時傳回 `409 agent_conversation_busy`，並以
`409 agent_conversation_archived` 拒絕已封存的對話。對話記錄卡片會標示
邊界，並說明較舊的資料列仍會保留，但會從活動脈絡中隱藏。

#### 分支

`POST .../fork` 接受可選的 `{at_entry_id?, title?}` 本文，並傳回 `201`
與新對話。`at_entry_id` 是包含該項目在內的截止點，必須屬於來源討論串；
預設為最新項目。預設標題為 `Fork of {source.title}`，裁切至 200 字元。
分支一律為使用中、取得新的 `provider_session_id`、記錄
`parent_conversation_id` 與 `fork_at_entry_id`，並以新的 ID 與
`commit_seq` 值複製截止點之前的不可變項目。開頭標記與脈絡編輯會重新
對應到複製的項目；截止點之外的參照會被丟棄。來源對話及其項目永遠不會
被修改。

分支只會複製對話記錄項目。執行、重試狀態與核准狀態不會被複製，因此
下一則使用者訊息會針對複製的脈絡開始全新的執行。已封存的來源會傳回
`409 agent_conversation_archived`；使用中的執行會傳回
`409 agent_conversation_busy`；來自另一個對話的截止點會傳回
`400 agent_fork_entry_invalid`；缺少或已軟刪除的來源會傳回
`404 agent_conversation_not_found`。在 UI 中，討論串側欄對使用中的
討論串有 **分支** 動作（已封存的討論串則停用並附上說明），且使用者／
助理項目會提供 **從此處分支**。成功時會顯示浮動提示、使討論串清單失效，
並導覽至新討論串；頁首會顯示 `Forked from #<id>`，並附上來源連結。

#### 頁面脈絡與 KV 快取

用戶端可以在訊息中送出一個 `page_context` 物件：

| 欄位 | 類型 | 規則 |
|---|---|---|
| `key` | 字串 | 穩定的頁面身分；1–512 字元 |
| `path` | 字串 | 人類可讀的路由加上有意義的查詢參數；1–1024 字元 |
| `title` | 字串或 null | 可選的頁面標題；最多 300 字元 |
| `text` | 字串 | 頁面上可見的純文字；伺服器裁切前為 1–12,000 字元 |

伺服器會正規化行尾與空白、合併重複的空白行，並將儲存的快照上限設為
6,000 字元。項目會在 `data` 中儲存 `page_key`、`path`、可選的 `title`、
`text_chars` 與 `truncated`，並在 `<page_context>` XML 封套內向模型送出
一則使用者角色訊息。系統提示詞會將該封套標記為資料，絕不會標記為指令。

頁面脈絡是僅附加且保留快取的：

- `begin_message` 會將傳入的鍵與最新脈絡邊界（壓縮或重設）當下或之後的
  最新 `pi.page-context` 項目相比。去重與 `last_page_context_key` 的範圍
  都限於該活動區段。
- 只有不同的鍵才會附加新快照。從同一個頁面再次提問不會重複附加。
- 壓縮或清除邊界會隱藏較早的快照，因此同一個頁面可以在邊界之後重新
  附加。
- 快照項目與使用者項目共用一個 `commit_seq`；快照會緊接在使用者項目
  之前，若同一回合同時寫入自動壓縮項目，則排在它之後。
- 較早的項目永遠不會被重寫，因此穩定的系統／工具前綴與先前的對話前綴
  仍是有效的 KV 快取系譜。壓縮或重設邊界則刻意開始新的系譜。

目前的 SPA 不會附加頁面快照，因為浮動面板與跨頁面輸入區已被移除。API
欄位仍提供給外部用戶端使用；當快照存在時，對話記錄會將它呈現為精簡的
脈絡卡片，而不是使用者問題。

測試會透過設定 `app.state.agent_chat_generator` 或覆寫
`get_agent_chat_generator`，從
`app/module/agent/test/fake_chat_generator.py` 注入確定性的
`FakeChatGenerator`；不會發出任何 DeepSeek 呼叫。

#### 已知限制

- 重試會以相同的執行階段快照原則啟動全新的執行，但不會提高任何預算。
  已經耗盡權杖或工具結果預算的對話記錄，可能再次觸及相同的上限。
- 核准處置是單寫入者。若程序在核准已被認領、但工具結果尚未附加之前
  崩潰，等待中的執行會在下一次啟動時封閉式失敗，而不是自動重試寫入。
- 關閉 `save_memory_requires_approval` 只會影響新的呼叫。在它開啟時建立的
  待處理核准會保持待處理，直到被明確核准或拒絕；設定變更永遠不會自動
  核准它們。

### 儲存的問題

`/api/v1/agent/questions` 是對話代理旁邊的一個小型問答庫。儲存的問題可以
在任何答案存在之前就存在。提問它會建立新對話、執行一個 JSON 代理回合，
並將結果寫回同一資料列，因此問題會保留穩定的 ID 與其最新答案。

| 方法 | 路徑 | 用途 |
|---|---|---|
| `GET` | `/api/v1/agent/questions?limit=&offset=` | 列出儲存的問題，最新優先；`limit` 為 1–100（預設 50） |
| `POST` | `/api/v1/agent/questions` | 儲存一個問題；`201`；只接受 `question` |
| `PATCH` | `/api/v1/agent/questions/{question_id}` | 編輯問題文字 |
| `DELETE` | `/api/v1/agent/questions/{question_id}` | 刪除問題及其儲存的答案；`204` |
| `POST` | `/api/v1/agent/questions/{question_id}/ask` | 執行一個回合並保存其結果 |

清單本文為 `{resources, total, limit, offset}`。全部五個操作都要求已驗證
的帳號，且只會揭露該帳號儲存的問題。建立與更新會拒絕未知欄位，因此
用戶端無法自行提供答案。`question` 會去除首尾空白，並限制為 32,000
字元。

資料表（`saved_question`）儲存：

- `id`、`question`、可為 null 的 `answer`，以及作為 JSONB 陣列的
  `citations`；
- 可為 null 的 `conversation_id`，搭配 `ON DELETE SET NULL`，因此刪除
  對話仍會保留儲存的答案；
- 最近一次提問的 `run_status`、`error_code` 與 `error_detail`；
- `created_at`、`updated_at` 與 `last_asked_at`。

`PATCH` 會將正規化後的文字與儲存的文字相比。問題若有變更，會清除
`answer`、`citations`、`conversation_id`、所有執行中介資料與
`last_asked_at`；未變更的編輯只會更新 `updated_at`。這可避免舊答案被
顯示在新的措辭之下。

`POST .../ask` 會建立一個以問題為標題的新對話（最多 80 字元）、附加
使用者項目、以現有的執行階段快照原則執行恰好一個代理回合，並記錄最終
答案、引用標記、對話 ID 與 `run_status`。供應商或工具失敗仍會是 `200`，
帶有 `run_status="failed"` 及其 `error_code`/`error_detail`，因此問題
會留存。缺少 AI 設定則會保留既有的 `503 agent_not_configured` 回應。
再次詢問同一個問題會建立另一個對話，並在同一筆儲存的資料列上取代答案。

`/questions` 頁面是次要工作區，從「搜尋」與方法頁尾連結。它使用產生的
hook，並提供建立、列出、分頁、編輯、刪除與提問動作。每張卡片會顯示其
狀態、答案、引用標籤、執行錯誤、上次提問時間，以及對話存在時的
**開啟對話** 連結。提問是同步的 JSON 請求，因此卡片會在回合所需的數秒
內顯示待處理狀態。

### 對話閱讀室

`/chat` 與 `/chat/:conversationId` 是代理的常駐閱讀室。討論串側欄會列出
使用中與已封存的對話，並支援重新命名、封存／還原、刪除與新增討論串；
版面上會將不可變的項目呈現為守藏者頁邊註記、典藏紙頁、田野筆記工具結果
與結構化資源卡片。輸入區會透過 SSE 串流，支援 Cmd/Ctrl+Enter 與停止
動作，並在執行結束時重新整理討論串清單與使用中的對話記錄（其他對話不會
重新取得）。

討論串卡片會為最近一次失敗／取消的助理回答、結尾的硬性上限工具結果
（`step_limit`、`token_limit`、`tool_call_limit` 或
`tool_result_budget_exhausted`），或助理項目之前的串流失敗顯示
**重試**。重試會呼叫既有的重試端點、重複使用同一個使用者項目、不附加
重複的訊息，並在串流進行中停用。`409 agent_run_not_retryable` 回應會
觸發對話記錄重新取得，讓過期的動作消失；重試可能會再次觸及相同的預算。

當執行因為 `save_memory` 而暫停時，討論串與浮動面板中會出現一張已保存的
核准卡片。它會顯示提議的記憶、取代／發生時間脈絡、寫入風險，以及
**核准寫入**／**拒絕** 動作。卡片會從可持久化的核准端點載入，因此能
承受重新載入；當處置正在串流或討論串已封存時，它會停用。核准會恢復
執行並附加真正的工具結果；拒絕會附加 `memory_rejected`，且永遠不會
寫入。

同一個工作台也會為使用中的脈絡提供 **壓縮** 與 **清除**。壓縮會立即
執行；清除會要求一次行內確認。兩者在串流進行中與已封存的討論串上都會
停用。`409 agent_conversation_busy` 回應會顯示穩定的錯誤訊息並重新取得
討論串。隨後的壓縮／重設邊界會呈現為脈絡卡片，而不是使用者訊息，且卡片
會說明較舊的對話記錄資料列仍會保留，但會從模型的活動脈絡中隱藏。

UI 會使用產生的 Orval hook 來處理對話中介資料與生命週期，並使用小型
`agent-stream.ts` 用戶端處理 `text/event-stream`，因為產生的 hook 會
解析一般的 JSON 回應。Markdown 會以 `skipHtml` 呈現；引用會解析至檔案庫
預覽或記憶閱讀器。儲存的問題仍可在 `/questions` 供之後的代理回合使用。

側欄是分組的，而不是平鋪的。典藏工作區會先出現（對話、檔案庫、時間軸、
記憶、搜尋、儀表板），接著是包含 **使用者個人檔案** 的個人區塊，然後是
系統區塊（設定、**變更密碼**、僅 root 帳號可見的 **帳號**、關於），以及
一個獨立的 **工作階段** 區塊，內含 **登出**。頁尾的身分識別也是 root
使用者切換器：root 點擊它會開啟可搜尋的帳號對話框，而一般帳號只會看到
單純的身分區塊。模擬期間，頁尾會保留目標帳號與一個小小的 **檢視身分**
標記，且頁面畫布上方會有常駐橫幅標明目標，並提供 **返回 root**，在結束
工作階段前會要求輸入 root 密碼。索引編號會依實際呈現位置計算，因此對
一般使用者隱藏帳號與切換器時不會留下空隙。root 的 `/` 會開啟對話；典藏
摘要位於 `/dashboard`，使用 `database` 側欄圖示。寬度低於 980 px 時，
側欄會變成從行動列開啟的導覽抽屜。

### 對話工作區

`/chat` 是固定高度的三欄工作區：可收合的對話抽屜、串流欄，以及工具
檢視器。12 px 的分隔線支援指標拖曳、點擊收合，以及鍵盤方向鍵／Home／
End；比例與收合狀態會保存在本機。寬度低於 900 px 時，檢視器會變成
分頁。輸入區按 Enter 送出、Shift+Enter 插入換行，並在串流時提供「停止」。

沒有第二個輸入區。先前的浮動面板與命令選擇區已被移除；儲存的問題會像
任何其他回合一樣透過 `/chat` 執行。

狀態泡泡描述可觀察的工作，而不是隱藏的思維鏈：定位、搜尋、閱讀、比對、
撰寫、儲存、緘封與錯誤。每個狀態列可以顯示步驟、工具名稱、經過時間、
狀態與簡短的結果摘要。

檢視器會讓使用者正在閱讀的資源留在畫面上。它會跟隨最新的工具呼叫，直到
使用者釘選某個面板；它提供 **跟隨目前** 以恢復跟隨，並在後續工具沒有
資源時保留最後一個有效資源。檢視器面板會重用與檔案庫、記憶閱讀器相同的
安全呈現器及檔案／記憶查詢，而不是新增第二條呈現路徑。

| 工具 | 檢視器構想 |
|---|---|
| `search_knowledge` | 跨檔案、記憶與摘要的結果星圖；摘錄可就地展開 |
| `read_file` | 手稿分塊視窗，附檔案 ID、分塊編號與引用 |
| `read_timeline` | 時間帶，附密度、取樣事件與略過數量 |
| `read_path` | 資料夾分支圖，可直接開啟資料夾或檔案 |
| `read_memory` | 壓花記憶鏈，附取代關係的相鄰項目 |
| `save_memory` | 火漆印收據，附狀態、記憶 ID 與被取代的 ID |
| `present_resource` | 展示架，會嵌入檔案或記憶檢視器 |

每個面板都提供載入、空白、錯誤與成功狀態。工具結果的 `data` 會帶有
有上限、僅供 UI 使用的摘錄與檢視器 URL，讓這些面板得以運作；面對供應商的
工具內容則維持不變。

對話檢視器、檔案庫工作區與資料夾看板已在目前版本中實作，且已提交的
`frontend/dist` 是重新建置的正式用戶端。進一步變更前端後，請重新建置並
提交 `frontend/dist`，因為 Docker 映像檔會提供已提交的用戶端，且不會
執行前端建置。

### 資源預覽

檔案會在檔案庫內的現地預覽彈出視窗中開啟；記憶閱讀器是 `/memory/:id`
上的一般路由。舊版的 `/viewer/*` URL 會重新導向至那些介面，因此舊引用與
書籤仍可運作。

| 資源 | 渲染器 |
|---|---|
| PDF | `react-pdf` 11 + 內附的 `pdfjs-dist` 6、頁面導覽、縮放、符合寬度、文字層 |
| DOCX | `docx-preview`，位於停用指令碼的沙箱中 |
| 圖片 | 使用標準檔案內容端點的原生圖片 |
| 文字／JSON／Markdown／CSV | 典藏頁面，支援換行／複製／下載、美化 JSON、GFM Markdown |
| 記憶 | 壓製紀錄的記憶葉片，附系譜與追溯連結 |

`GET /api/v1/files/{file_id}/content` 會以 `nosniff`、沙箱化 CSP、
ETag/Last-Modified 與單一範圍 HTTP Range 支援（`206`/`416`；
`If-None-Match` 傳回 `304`）行內提供原始檔。`/download` 仍為附件。
純文字紀錄的 `has_original=false`；這類頁面會完全略過 `/content` 探查，
並讀取已索引的分塊。

PDF.js 的 CMaps 與標準字型會由 `bun run pdf-assets` 從固定版本的
`pdfjs-dist` 套件複製到 `frontend/public/pdfjs/`，`dev` 與 `build` 會
自動執行此動作。Vite 會將它們輸出到 `frontend/dist/pdfjs/`；由於 Docker
映像檔會複製已提交的 `frontend/dist` 且不執行前端建置，這些輸出資產必須
與 `dist/` 的其餘部分一起提交。它們會在本機提供，且永遠不會從 CDN 取得。

### 帳號、角色與工作階段

第一次造訪時，應用程式會要求你建立 root 帳號。沒有預設密碼，也沒有電子
郵件復原。root 接著可以從 **帳號** 建立一般帳號；新帳號會以產生的 20
字元臨時密碼建立，該密碼只顯示一次，且帳號必須在任何典藏內容載入之前
選擇新密碼。root 可以停用、啟用、重設及模擬其他帳號。停用帳號或重設其
密碼會撤銷其工作階段；撤銷會在請求開始時檢查，因此已經在串流的 SSE
回合可能會完成目前的執行。帳號永遠不會被刪除，因此使用者名稱會一直
保留。

**帳號** 現在使用較大的資訊卡片。每張卡片帶有頭像、名稱與 `@username`、
角色／狀態標籤、建立日期、上次登入，以及該帳號彙總的代理用量：總計、
提示、完成與快取權杖、API 呼叫、回合與最後活動。提示／完成的劃分會以
小型長條圖呈現，而沒有代理活動的帳號仍會顯示可讀的零狀態。用量會依每次
代理執行計數，並由資料庫觸發程序彙總，因此卡片仍只是低成本的 root 專用
清單讀取，而不是跨帳號的對話掃描。

root 可以從頁尾使用者切換器或一般使用中帳號卡片開始模擬工作階段。對話框
會在本機搜尋 root 專用的帳號清單、排除 root 帳號，並拒絕已停用或必須
變更密碼的帳號。模擬是 root 刻意保留的受信任能力：cookie 會變成目標
帳號的工作階段，並帶有 `impersonator_user_id` 標記，目標的角色會控制
每一項一般授權決定，且僅限 root 的頁面會消失。常駐橫幅會標明目標，並
提供 **返回 root**，這需要 root 密碼、刪除模擬工作階段，並發出全新的
root 工作階段。要求密碼可防止被模擬的人接管 root。模擬期間會拒絕變更
密碼。一個分頁中的工作階段轉換會重新載入其他分頁，因此過期的 DOM、
草稿、對話框與帳號範圍的查詢資料列都無法留存；上次對話的接續指標也會
被清除。這不是 RLS 繞過；它只是最高信任帳號以另一人身分行動的另一種
方式，就像重設該帳號的密碼一樣。

兩種角色都使用相同的私人典藏介面。root 另外管理帳號與全域設定，但不是
資料超級使用者：API 與 PostgreSQL 資料列級安全性會防止它透過一般查詢
讀取另一個帳號的檔案、記憶或對話。密碼重設與明確模擬是受信任的復原
例外：root 可以發出臨時密碼或開啟目標的工作階段，因此能以該帳號登入。
請據此保護 root 憑證；RLS 並不是用來防禦惡意 root 使用那些能力的機制。
一般使用者看不到全域設定分頁或 **帳號** 頁面；他們的設定只會顯示
**常用提示詞** 與 **語言**，而 root 會看到全部八個分頁。儀表板與統計
計數的範圍限於登入的帳號；AI 狀態是全域且唯讀的。密碼會以 Argon2
雜湊；資料庫只儲存每個工作階段權杖的 SHA-256 雜湊。cookie 為 HttpOnly、
SameSite=Lax，並在 `APSOR_COOKIE_SECURE=true` 時為 Secure（Cloudflare
compose 會設定它）。每個帳號都可以在 `/profile` 編輯其顯示名稱與任意
數量的有序標題／內容個人檔案卡片；名稱會標示對話回合，卡片則會作為
`user_profile` 系統區段凍結到新對話中。登入用的使用者名稱維持不可變。

| 方法 | 路徑 | 用途 |
|---|---|---|
| `GET` | `/api/v1/auth/status` | 首次執行狀態與目前工作階段 |
| `POST` | `/api/v1/auth/setup` | 建立 root 帳號（僅限首次執行） |
| `POST` | `/api/v1/auth/login` | 驗證密碼並設定工作階段 cookie |
| `POST` | `/api/v1/auth/logout` | 刪除工作階段並清除 cookie |
| `POST` | `/api/v1/auth/password` | 變更登入者的密碼；在強制變更期間允許 |
| `GET` | `/api/v1/auth/me` | 目前帳號（需要工作階段） |
| `GET` | `/api/v1/auth/profile` | 顯示名稱加上每張有序的個人檔案卡片 |
| `PUT` | `/api/v1/auth/profile` | 以原子方式取代顯示名稱與所有卡片 |
| `GET` | `/api/v1/accounts` | 列出每個帳號，root 優先（僅限 root） |
| `POST` | `/api/v1/accounts` | 建立一般帳號並傳回一次性臨時密碼（僅限 root） |
| `POST` | `/api/v1/accounts/{user_id}/disable` | 停用帳號並撤銷其工作階段（僅限 root） |
| `POST` | `/api/v1/accounts/{user_id}/enable` | 重新啟用帳號（僅限 root） |
| `POST` | `/api/v1/accounts/{user_id}/reset-password` | 取代另一個帳號的密碼（僅限 root） |
| `POST` | `/api/v1/accounts/{user_id}/impersonate` | 將 root cookie 取代為一般目標帳號的工作階段（僅限 root） |
| `POST` | `/api/v1/auth/impersonation/stop` | 驗證 root 密碼、刪除模擬工作階段，並發出全新的 root 工作階段 |

每個知識、設定、提示詞與代理端點都要求已登入且使用中的帳號。僅限 root
的設定與帳號路由會對一般使用者傳回 `403 forbidden`，而
`must_change_password=true` 的工作階段在變更密碼之前，只能存取驗證狀態、
變更密碼與登出端點。只有 `/api/v1/health`、`/health`、
`/api/v1/auth/status`、`/api/v1/auth/setup`、`/api/v1/auth/login`、
`/api/v1/auth/logout`、`/api/docs`、`/api/redoc`、`/openapi.json` 與 SPA
外殼是公開的。工具端點也需要工作階段 cookie。

文件匯入（`POST /api/v1/files`）支援：

- **圖片**（`jpg`、`jpeg`、`png`、`webp`）—— 設定後使用 DeepSeek 視覺
  圖說 + OCR；否則使用由檔名衍生的圖說，並設定
  `extraction_method=filename`。圖片仍是普通的檔案庫檔案。
- **PDF** —— 先使用 pypdf 文字；當文字為空、亂碼，或 AI 結構化分析指出
  `use_vision` 時，以 pypdfium2 呈現最多 10 頁並執行視覺 OCR。
- **DOCX** —— python-docx 段落與表格；內嵌圖片可提供視覺備援。
- **TXT / MD / CSV / JSON / LOG** —— 直接文字加上 AI 結構化中介資料
  （標題、摘要、標籤、document_type）。

相同的匯入也可以透過 `POST /api/v1/files/async` 與
`POST /api/v1/files/text/async` 非同步使用；請輪詢
`GET /api/v1/files/ingest-jobs/{id}` 取得階段與分塊進度。請見上方的
**資料匯入執行階段**。

互動式文件：<http://127.0.0.1:8000/api/docs>。OpenAPI 結構描述是已提交
Orval 用戶端的來源。

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

## 檢索如何運作

1. **正規化** 使用 NFKC 與小寫。標點會變成空白。
2. **建立索引** 重疊的 CJK 雙字組、拉丁詞彙與拉丁三字元序列。每個分塊會
   儲存一份唯一的 n-gram 清單與詞頻。
3. **BM25** 為候選項目評分（`k1=1.2`、`b=0.75`）。像 `automobile ford`
   這樣的聯集查詢會自然偏好同時包含兩個詞的分塊。
4. **向量召回** 預設使用 384 維的帶符號特徵雜湊嵌入器，因此可離線運作。
   設定 `APSOR_EMBEDDING_PROVIDER=openai` 與相符的基礎 URL／模型，即可
   改用託管的嵌入模型。
5. **融合** 使用倒數排名融合。每種來源種類會保留自己的前
   `result_number` 名，因此摘要不會被檔案分塊擠掉。
6. **去重** 依分塊 ID，然後補齊檔案、記憶或摘要資料列。

若向量召回無法使用，搜尋仍會傳回 BM25 結果。同步匯入在嵌入呼叫於重試
預算內失敗時，會讓分塊維持純文字；可持久化的 worker 會將耗盡重試的嵌入
視為工作失敗，因此不會發佈部分檔案。

### 我需要嵌入模型的金鑰嗎

不需要。預設的帶符號特徵雜湊嵌入器可離線執行，並提供真正的詞彙向量
召回。CJK 雙字組上的 BM25 可處理精確詞彙與人名。若你想要語意或跨語言
召回，請將服務指向 OpenAI 相容的嵌入端點：

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

設定頁也可以將此設定存放在資料庫中。變更嵌入模型之後，請開啟設定並執行
**重新嵌入檔案庫**（或呼叫
`POST /api/v1/settings/providers/embedding/reindex`），讓現有分塊取得新
維度的向量。在那之前，文字搜尋仍可運作，而向量搜尋會略過不相容的分塊。

### 什麼是帶符號雜湊嵌入器

它是一個確定性的特徵雜湊向量化器，不是訓練過的神經網路模型。每個詞元
（CJK 雙字組、拉丁詞彙或拉丁三字元序列）都會以 BLAKE2b 雜湊到 384 個桶
之一。雜湊摘要的一個位元會成為正負號，因此碰撞會部分抵消，而不是總是在
一起累加。桶值會累積，向量則會進行 L2 正規化。

```text
token -> BLAKE2b -> bucket 0..383 + sign(+1/-1) -> accumulate -> normalize
```

結果：

- **沒有模型下載、沒有 GPU、沒有金鑰。** 它在 CPU 上執行，每個分塊只需
  數微秒，且每個向量只需數 KB 的 RAM。
- **詞彙層面，而非語意。** `car` 與 `automobile` 是不同的詞元。BM25 能
  處理精確詞彙，但查詢措辭會有影響。
- **確定性。** 相同的文字永遠產生相同的向量，這讓匯入與測試可重現。
- **個人規模的精確掃描。** 目前實作會掃描最多 20,000 個目前向量，並以
  Python 計算餘弦相似度。在較大的語料規模下，請以 pgvector/HNSW 或託管
  的嵌入模型取代它；`EmbedderProtocol` 邊界維持不變。


## 資料模型

結構描述遵循三項規則：來源中介資料留在其擁有的資料表中，統一的分塊資料表
只儲存來源鍵，且每個私人資料列恰好帶著一個擁有者。

```text
file ─────────────┐
folder ───────────┤
memory ───────────┼──> chunk ──> chunk_ngram
memory_summary ───┘
```

下列私人典藏資料表帶有 `user_id bigint NOT NULL`。例外是全域設定資料表
（`agent_config`、`ingest_config`、`system_prompt_section` 與四張供應商
資料表），它們是共用的部署設定，以及驗證資料表（`app_user`、
`user_session`），它們保存的是身分而非典藏內容。私人資料表中的父／子
連結使用複合 `(id, user_id)` 外鍵，因此資料列無法指向另一個帳號的系譜。
`apsor_app` 角色上的強制 PostgreSQL 資料列級安全性是資料庫層的後盾；
請求交易會在一次交易期間設定 `app.user_id`。驗證資料表刻意留在 RLS
之外，因為登入與工作階段查詢發生在使用者脈絡存在之前；全域設定資料表
則是全體可讀／root 可寫。

- `file`：每個版本一列。`is_current` 與 `deleted_at` 是軟狀態；ID 永遠
  不會重複使用。檔案葉不會在資料夾資料表中重複：它們的位置是
  `raw_file_path`。`storage_backend` 會為原始位元組記錄 `local` 或 `r2`，
  且只有在 `storage_key` 為 null 時才為 null。
- `folder`：明確的資料夾紀錄（`parent_id`、`path`、`name`、`depth`）。
  空資料夾與資料夾身分會獨立於檔案存活。唯一性是依帳號區分：
  `(user_id, path)`。
- `chunk`：`(source_kind, source_id, chunk_index)`，附帶可選的 JSONB
  向量。
- `chunk_ngram`：BM25 使用的倒排索引。
- `memory`：線性時間軸，附自動產生的 `title`、`supersedes_ids`、
  `superseded_by_id`、`status=active|deprecated`，以及直接汰除的來源資訊
  `deprecated_at` / `deprecated_reason`。已汰除的資料列必須有後繼者或
  `deprecated_at` 時間戳記。
- `memory_summary`：期間、來源記憶 ID、主題、產生器與模型。
- `chat_provider_config` / `embedding_provider_config` /
  `web_search_provider_config` / `web_fetch_provider_config`：每個儲存的
  供應商一列，附加密的 API 金鑰、安全提示，以及模型／基礎 URL／維度。
  `is_active` 上的部分唯一索引會強制每種能力只有一個使用中的資料列。
  `web_search` 與 `web_fetch` 是獨立的憑證。
- `app_user`：每個帳號一列。`role` 為 `root` 或 `user`；`is_active`、
  `must_change_password`、`disabled_at`、`created_by_user_id` 與密碼稽核
  時間戳記描述帳號生命週期。部分唯一索引會強制恰好一個 root，且使用者
  名稱會維持全域唯一且不可變。
- `user_profile_card`：描述帳號的有序標題／內容卡片；整組卡片會作為
  `user_profile` 區段凍結到新對話中。
- `frequently_used_prompt`：供空白對話頁使用的私人、帳號可編輯捷徑，依
  `sort_order` 排序，每帳號上限為 20 列。
- `agent_conversation` / `agent_entry` / `agent_run`：常駐代理的對話記錄
  範圍、不可變的項目記錄，以及每次提交的執行狀態。`agent_commit_seq` 會
  將同一交易中寫入的項目分組。頁面快照是同一份記錄中的
  `pi.page-context` 項目，而不是另一張資料表。
- `agent_approval`：針對需要確認的寫入，保存可持久化的待處理／已核准／
  已拒絕／已過期人工決定，附經驗證的引數、安全預覽，以及用來恢復等待中
  執行的迴圈快照。
- `agent_config`：一列（`id=1`），帶有代理迴圈與設定 API 使用的經驗證
  執行階段限制。
- `saved_question`：帳號的問答庫。`question` 由使用者撰寫；`answer`、
  `citations`、`conversation_id` 與執行狀態／錯誤欄位只會由提問寫入。
  `conversation_id` 使用 `ON DELETE SET NULL`，而 `last_asked_at` 會記錄
  最近一次嘗試。
- `file_ingest_job`：可持久化的匯入佇列。它儲存來源種類、路徑、酬載鍵與
  後端、狀態／階段、`progress_pct`、分塊計數、有上限的錯誤欄位，以及嘗試
  次數／時間戳記。每個帳號的每個路徑只能有一個使用中的工作。工作會指向
  其暫存檔案、在失敗時清除該連結，且檔案與分塊只會在工作發佈它們時才
  成為目前版本。
- `ingest_config`：一列（`id=1`），帶有經驗證的 worker 輪詢、擷取、
  進行中工作、嵌入與分塊大小設定。它不是分塊來源；佇列會參照最終發佈
  的檔案。

原始位元組不會存放在 PostgreSQL 中。它們位於本機磁碟或私人 R2 儲存桶，
由 `storage_backend` 依檔案選擇；擷取出的分塊及其 n-gram 則留在
PostgreSQL。

已提交的程式碼、註解、UI 文案與文件皆為英文。

## 開發檢查

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

整合測試套件在相同執行個體上使用一個真實的 PostgreSQL 測試資料庫
（`apsor_archive_test`）、依序執行，並在每次測試之間重設每張受追蹤的
資料表。資料庫是由 `alembic upgrade head` 建置，而不是 `create_all`，
因此 `apsor_app` 角色、授權與 RLS 原則會出現在每個請求中。共收集 46 項
測試；每項都會演練真實的 HTTP 介面與資料庫。多使用者測試涵蓋 root／
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

最新的移轉是 `f9c2a7d4e6b1`，在 `e8f1c4d2a7b9` 之後。此分支上
`agent_config` 之後的移轉為：

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
- `f9c2a7d4e6b1`（目前 head）將每次執行的權杖／API 呼叫計數器加入
  `agent_run`、將每帳號彙總加入 `app_user`、加入用量差值觸發程序，以及
  可為 null 的 `user_session.impersonator_user_id` 模擬標記。它會從助理
  項目的 JSON 回填歷史用量，且強制 RLS 回填需要超級使用者／BYPASSRLS
  的移轉角色。

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
  dist/                         committed production build served by FastAPI
docker-compose.yml              normal deployment
docker-compose.dev.yml          local dependencies
docker-compose.cloudflare-tunnel.yml   Cloudflare Tunnel deployment
docs/cloudflare-tunnel.md       Tunnel deployment, backup, and security guide
docker/caddy/                   non-root reverse proxy for the tunnel
```

## 安全性與隱私

- 在對外暴露服務之前，請先完成首次執行設定。當沒有任何帳號存在時，
  `/api/v1/auth/setup` 依設計是公開的；請勿在 root 帳號建立之前，讓全新
  的執行個體透過 tunnel 對外可達。
- 一個 root 加上一般帳號可保護典藏。密碼會以 Argon2 雜湊；工作階段權杖
  只會以 SHA-256 雜湊存放於 `user_session`。cookie 為 HttpOnly、
  SameSite=Lax，並在 `APSOR_COOKIE_SECURE=true` 時為 Secure。臨時密碼
  只會傳回一次，永遠不會被記錄或快取，且帳號必須在載入內容之前變更它。
- 每個私人資料列都帶有 `user_id`；複合外鍵會將系譜留在同一個帳號內，
  且 `apsor_app` 上的 PostgreSQL 強制資料列級安全性即使少了服務篩選
  條件，也會拒絕跨帳號的讀取與寫入。僅限 root 的路由防護會保護帳號與
  全域設定，但 root 不是資料超級使用者，無法透過一般 API 查詢讀取另一個
  帳號的典藏。root 密碼重設與明確模擬是刻意保留的受信任復原能力，可能
  將登入存取權轉移給目標帳號；停止模擬需要 root 密碼、會刪除該
  工作階段，並發出全新的 root 工作階段。請將 root 視為最高信任憑證，且不要
  把 RLS 當成防禦惡意 root 的機制。
- **RLS 是應用程式邊界，不是主機邊界。** 部署登入是供移轉與維護使用的
  PostgreSQL 超級使用者；應用程式會為請求交易切換至 `apsor_app`。任何
  本機作業系統使用者、任何位於資料庫／快取網路上的容器，或任何能讀取
  `.secrets/`/`.env` 的人，都能繞過 API 與 RLS。請保持主機受信任、將
  資料庫與快取綁定至 localhost 或內部網路、使用不同的主機帳號、為任何
  共用主機設定高強度的資料庫／快取密碼，並在暴露後輪替憑證。未來的強化
  步驟是專用的非超級使用者執行階段登入，加上分開的維護憑證。
- 一般 Compose 檔案會將 API 綁定至 `127.0.0.1`；Cloudflare 檔案不發佈
  任何主機連接埠。登入節流是記憶體內實作，因此僅限單一程序；請執行一個
  API 程序，或在擴充前將節流移至 Valkey。
- 路徑會拒絕穿越區段、反斜線、控制字元與過長的值。上傳上限為 10 MB，
  且僅限於副檔名允許清單。
- 來自檔案與記憶的 HTML 會透過 React 以文字呈現。代理 Markdown 使用
  `skipHtml`；DOCX 預覽會在停用指令碼的沙箱中執行。UI 永遠不會使用
  `dangerouslySetInnerHTML`。
- DeepSeek 金鑰位於 `.secrets/deepseek.env` 或環境中。它永遠不會被
  記錄、傳回或提交。從設定頁儲存的金鑰會在 PostgreSQL 中加密，且只會
  以四字元提示傳回。
- R2 憑證位於已列入 gitignore 的 `.secrets/r2.env`，以唯讀方式掛載，
  且永遠不會成為容器環境變數。儲存桶是私人的，沒有預先簽署或公開 URL。
- AI 呼叫會發生在摘要與代理回合。若供應商失敗，API 會傳回穩定的錯誤，
  而不是編造答案。

## 授權

MIT。請見 `LICENSE`。
