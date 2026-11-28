# 系統架構

[English](../architecture.md) · **繁體中文** · [简体中文](../zh-CN/architecture.md)

## 技術堆疊

| 層次 | 選擇 |
|---|---|
| API | Python 3.13、FastAPI、SQLAlchemy 2 async、Alembic、psycopg 3 |
| 儲存 | PostgreSQL 17（`pg_trgm` 用於路徑模糊搜尋）；原始位元組位於 RustFS（預設）、Cloudflare R2、任何 S3 相容儲存桶或本機磁碟 |
| 快取 | Valkey／相容於 Redis，附記憶體內備援 |
| 檢索 | CJK 雙字組 + 拉丁詞元 n-gram、BM25、帶符號雜湊向量、RRF |
| AI | DeepSeek `deepseek-flash`、Anthropic Claude，或任何 OpenAI 相容的對話端點 |
| 前端 | React 19、TypeScript、Vite、React Router、React Query、Orval |
| 部署 | Docker Compose（Caddy + Cloudflare Tunnel），或使用 `uv` 的裸機部署 |

## 檢索如何運作

1. **正規化** 使用 NFKC 與小寫。標點會變成空白。
2. **建立索引** 重疊的 CJK 雙字組、拉丁詞彙與拉丁三字元序列。每個分塊會
   儲存一份唯一的 n-gram 清單與詞頻。
3. **BM25** 為候選項目評分（`k1=1.2`、`b=0.75`）。像 `automobile ford`
   這樣的聯集查詢會自然偏好同時包含兩個詞的分塊。
4. **向量召回** 預設使用 384 維的帶符號特徵雜湊嵌入器，因此可離線運作。
   設定 `APSOR_EMBEDDING_PROVIDER=openai` 與相符的基礎 URL／模型，即可
   改用託管的嵌入模型。
5. **融合** 使用倒數排名融合。每種典藏來源種類會保留自己的前
   `result_number` 名，因此摘要不會被檔案分塊擠掉。
6. **去重** 依分塊 ID，然後補齊檔案、記憶或摘要資料列。
7. **對話歷史** 走另一條扁平索引通道。每則超過 256 字元的使用者或助理訊息
   會切成 256 字元、32 字元重疊（步幅 224）的視窗。查詢嵌入會依餘弦相似度
   取前 128 個視窗；BM25 為每個召回的視窗評分；倒數排名融合會重新排序聯集，
   並保留前 15 名。無論典藏歷史開關為何，歷史視窗一律納入。每個命中結果都
   帶有穩定的 `agent_entry` ID，代理會以 `history_message` 展開它。已刪除的
   對話會被標記為非目前，並從這條通道消失。

若向量召回無法使用，搜尋仍會傳回 BM25 結果。嵌入失敗絕不會遺失段落：
當供應商額度用完（例如 OpenAI 的 `insufficient_quota`）、拒絕金鑰、無法連線，
或帳號的嵌入用量額度已用完時，每一條匯入路徑（可持久化的 worker 工作、同步
文字、Markdown 編輯、記憶、摘要與對話歷史）仍會儲存分塊的文字與 n-gram，
讓關鍵字搜尋立刻找得到，並把向量標為*待補*（`embedding IS NULL`）。專屬
worker 的 `EmbeddingBackfill` 迴圈（`APSOR_EMBEDDING_BACKFILL_ENABLED`，預設
開啟）會自動補上待補的向量：

- 供應商錯誤（帳務、額度、驗證、速率限制、服務中斷）會讓迴圈以指數退避暫停，
  最長 30 分鐘，而且不會算到段落頭上。退避結束後會自動恢復；嵌入供應商設定
  變更時，或 root 在儲值後於系統通知按下**立即重試**時，會立刻恢復。
- 嵌入用量額度已用完的帳號會先略過，直到 root 提高額度或週期重置；補嵌入
  和其他嵌入一樣會記錄用量。
- 被供應商以輸入錯誤拒絕的段落（HTTP 400/413/422）會單獨重試，最多五次，
  之後只保留關鍵字搜尋。

root 可以在系統通知看到待補數量、worker 狀態與下次重試時間
（`GET /api/v1/system/embedding-backfill`；`POST
/api/v1/system/embedding-backfill/retry`）。只有在可持久化工作進行中，供應商
重新載入後會改變模型或維度時，該工作才會失敗，避免同一個檔案混用兩種向量空間。

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
memory_summary ───┤
agent_entry ──────┘  (source_kind = history)
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
  `raw_file_path`。`storage_backend` 會為原始位元組記錄 `local`、`r2` 或 `s3`，
  且只有在 `storage_key` 為 null 時才為 null。
- `folder`：明確的資料夾紀錄（`parent_id`、`path`、`name`、`depth`）。
  空資料夾與資料夾身分會獨立於檔案存活。唯一性是依帳號區分：
  `(user_id, path)`。
- `chunk`：`(source_kind, source_id, chunk_index)`，附帶可選的 JSONB
  向量。`source_kind` 是 `file`、`memory`、`summary` 或 `history`；歷史分塊的
  `source_id` 是不可變的 `agent_entry` ID，內容是一個原始的 256 字元視窗。
- `chunk_ngram`：BM25 使用的倒排索引。
- `memory`：線性時間軸，附自動產生的 `title`、`supersedes_ids`、
  `superseded_by_id`、`status=active|deprecated`，以及直接汰除的來源資訊
  `deprecated_at` / `deprecated_reason`。已汰除的資料列必須有後繼者或
  `deprecated_at` 時間戳記。
- `memory_summary`：期間、來源記憶 ID、主題、產生器與模型。
- `chat_provider_config` / `embedding_provider_config` /
  `web_search_provider_config` / `web_fetch_provider_config`：每個儲存的
  供應商一列，附加密的 API 金鑰、安全提示，以及模型／基礎 URL／維度。
  `chat_provider_config` 另外儲存選用的 `max_output_tokens`，並接受
  `anthropic`、`deepseek`、`openai-compatible` 與 `none`；對話資料列是
  帳號所指派的端點。`is_active` 上的部分唯一索引會強制每種能力只有一個
  使用中的資料列。`web_search` 與 `web_fetch` 是獨立的憑證。
- `app_user`：每個帳號一列。`role` 為 `root` 或 `user`；`is_active`、
  `must_change_password`、`disabled_at`、`created_by_user_id` 與密碼稽核
  時間戳記描述帳號生命週期。八個指派欄位是 `chat_provider_config_id`、
  `chat_model`、`chat_reasoning_effort`、`aux_provider_config_id`、
  `aux_model`、`aux_reasoning_effort`（非 null，預設 `low`）、
  `chat_context_window_tokens` 與 `chat_compaction_threshold_tokens`。部分
  唯一索引會強制恰好一個 root，且使用者名稱會維持全域唯一且不可變。
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
  執行階段限制，包含壓縮範本與輸出上限，以及升級開關。
- `saved_question`：帳號的問答庫。`question` 由使用者撰寫；`answer`、
  `citations`、`conversation_id` 與執行狀態／錯誤欄位只會由提問寫入。
  `conversation_id` 使用 `ON DELETE SET NULL`，而 `last_asked_at` 會記錄
  最近一次嘗試。
- `file_ingest_job`：可持久化的匯入佇列。它儲存來源種類、路徑、酬載鍵與
  後端、狀態／階段、`progress_pct`、分塊計數、有上限的錯誤欄位，以及嘗試
  次數／時間戳記。每個帳號的每個路徑只能有一個使用中的工作。工作會指向
  其暫存檔案、在失敗時清除該連結，且檔案與分塊只會在工作發佈它們時才
  成為目前版本。
- `file_thumbnail`：每個檔案版本一張極小的 WebP，以 `file_id` 為鍵，帶有
  `status`（`ready`、`none` 或 `failed`）、像素尺寸、SHA-256、產生器版本與
  嘗試次數。它會隨其檔案一併串聯刪除。
- `companion` / `companion_frame` / `companion_preference`：帳號的自訂對話
  夥伴、每個動作經編碼的 AVIF（或 WebP）影格及其位置、大小與 SHA-256，以及
  帳號的夥伴選擇、是否顯示、動態程度與位置。
- `companion_story` / `companion_lore_fragment` / `companion_bond`：帳號依語言
  覆寫的夥伴人設與傳說、其片段，以及解鎖更深層傳說的完成對話數。
- `ingest_config`：一列（`id=1`），帶有經驗證的 worker 輪詢、擷取、
  進行中工作、嵌入與分塊大小設定。它不是分塊來源；佇列會參照最終發佈
  的檔案。

原始位元組不會存放在 PostgreSQL 中。它們位於本機磁碟、私人 R2 儲存桶，或
S3 相容儲存桶（預設為 RustFS），由 `storage_backend` 依檔案選擇；擷取出的分塊及其 n-gram 則留在
PostgreSQL。

程式碼、註解與文件以英文撰寫，英文為標準版本。介面與本 README 也提供完整的
繁體中文與簡體中文翻譯，並與英文來源一起更新。
