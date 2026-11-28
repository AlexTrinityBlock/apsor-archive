# 設定

[English](../configuration.md) · **繁體中文** · [简体中文](../zh-CN/configuration.md)

### 在應用程式內設定供應商

設定頁是設定供應商的標準方式，且只有 root 帳號能編輯全域登錄。它會寫入
四張各自獨立的能力資料表，因此一種能力永遠不會覆寫另一種：

- **對話** —— `chat_provider_config`：DeepSeek、Anthropic Claude 或任何
  OpenAI 相容的對話端點。對話資料列是帳號所指派的 **端點**；它有選用的
  `max_output_tokens` 上限（256–131,072）。
- **嵌入** —— `embedding_provider_config`：離線的 `hashing`、`openai` 或
  `openai-compatible`。多個資料列可以組成一條鏈結，但每個使用中的資料列都
  必須使用相同的模型與維度。
- **網路搜尋** —— `web_search_provider_config`：Tavily、Exa 或 DeepSeek。
  多個資料列可以同時使用中，組成一條有順序的鏈結。
- **網路取得** —— `web_fetch_provider_config`：Tavily `extract`、Exa
  `contents` 或 DeepSeek `fetch`。網路搜尋與網路取得刻意分成不同資料列，
  因此它們可以使用不同的供應商或不同的憑證。

每張資料表都儲存從零開始的 `priority`，並對 `priority WHERE is_active` 設有
部分唯一索引。對嵌入、網路搜尋與網路取得而言，鏈結中的第一列是主要，其餘
是備援；只有在供應商或傳輸失敗時才會前進到下一列，且所有資料列都失敗後
操作才失敗。對話不同：每個帳號會指派到一個明確的對話資料列，代理回合永遠
不會容錯移轉到另一個對話資料列。嵌入備援必須共用主要的模型與維度，因為
混合向量空間會損壞每位擁有者的索引。刪除資料列不會重複使用其身分 ID。

供應商資料列屬於全域部署設定：只有 root 帳號可以列出、編輯、測試或刪除
它們，一般使用者永遠不會收到供應商祕密或全域執行階段設定。API 永遠不會
傳回明文金鑰：瀏覽器只會收到例如 `...14f8` 的提示。`APSOR_SECRET_KEY`
提供 Fernet 主金鑰。若未設定，會在 `data/.secret_key`（Docker 中為
`/data/.secret_key`）建立 `0600` 權限的金鑰檔案，因此加密值能承受重新
啟動。`APSOR_TAVILY_API_KEY` 是兩種網路能力可選的環境備援。Exa 金鑰可以
放在已列入 gitignore 的 `.secrets/exa.env` 中，名為 `EXA_API_KEY`（或
`APSOR_EXA_API_KEY`）；加密的供應商資料列仍然優先。對話所用的同一個
`APSOR_DEEPSEEK_API_KEY` 也是 DeepSeek 網路搜尋與網路取得供應商的環境備援，
因此不需要另外的網路憑證。Anthropic 金鑰可以放在 `.secrets/anthropic.env`
中，名為 `ANTHROPIC_API_KEY`（或 `APSOR_ANTHROPIC_API_KEY`）；端點資料列上的
資料庫金鑰仍然優先。

對話端點擁有其金鑰，而不是帳號。多個帳號可以共用一個端點，輪替或清除該
端點的金鑰會影響每個指派到它的帳號。沒有加密金鑰的資料列可以使用供應商
範圍的環境金鑰作為資料列補充，但沒有每位使用者的金鑰，也沒有部署全域的
對話備援：未指派的帳號永遠不會被另一個使用中的資料列或單獨的環境金鑰
拯救。

嵌入、網路搜尋與網路取得的優先順序為：**使用中的資料庫鏈結 → 環境 →
內建預設值**。就對話而言，帳號指派會依 ID 選取端點資料列；供應商範圍的
環境金鑰只能補足該資料列。設定頁會標示每個供應商的來源與鏈結順序。變更
嵌入模型不會重寫現有向量；`reindex_required` 會提出警告。請執行 **重新
嵌入檔案庫**（或 `POST /api/v1/settings/providers/embedding/reindex`）來
更新目前的分塊。向量搜尋會略過維度與目前嵌入器不符的分塊。

供應商登錄 API：

| 方法 | 路徑 | 用途 |
|---|---|---|
| `GET` | `/api/v1/settings/providers` | 四個能力群組、遮蔽提示、有順序的鏈結、重新索引建議 |
| `POST` | `/api/v1/settings/providers/{capability}` | 建立一個儲存的供應商；可選擇將其附加到鏈結 |
| `PUT` | `/api/v1/settings/providers/{capability}/{provider_id}` | 取代一個儲存的供應商，不重新排序鏈結 |
| `DELETE` | `/api/v1/settings/providers/{capability}/{provider_id}` | 刪除一個儲存的供應商並補上鏈結空缺 |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/activate` | 附加該資料列，或傳入 `priority=0` 使其成為主要 |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/deactivate` | 從鏈結移除一個資料列並補上空缺 |
| `POST` | `/api/v1/settings/providers/{capability}/deactivate` | 清除整個鏈結；嵌入／網路退回環境／預設值，對話指派則變為未啟用 |
| `POST` | `/api/v1/settings/providers/{capability}/{provider_id}/test` | 送出一個小型供應商請求並測量延遲 |
| `POST` | `/api/v1/settings/providers/embedding/reindex` | 以使用中的供應商重新嵌入每個目前的分塊 |

`{capability}` 是 `chat`、`embedding`、`web_search` 或 `web_fetch` 之一。
登錄回應會在 `providers` 快取範圍下快取 30 秒；每次供應商寫入都會更新該
範圍。

當整條鏈結都失敗時，API 與 worker 會記錄一筆經過清理的
`provider_error_notice` 資料列，root 會在帳號頁看到它。通知會在 15 分鐘的
視窗內依能力、操作與錯誤代碼去重；重複發生時 `count` 與 `last_seen_at` 會
前進。這張資料表只保存供應商中繼資料，絕不保存提示詞或典藏內容。root 可以
列出通知、解決單一通知，或全部解決：

| 方法 | 路徑 | 用途 |
|---|---|---|
| `GET` | `/api/v1/system/provider-notices?status=open\|all&limit=50` | 未解決的通知與未解決數量 |
| `POST` | `/api/v1/system/provider-notices/{notice_id}/resolve` | 解決一則通知 |
| `POST` | `/api/v1/system/provider-notices/resolve-all` | 解決所有未解決的通知 |

### 每位帳號的模型指派

每個帳號都有兩個對話插槽。**主要** 插槽負責代理對話。**輔助** 插槽負責
摘要、記憶彙整、匯入標題與標籤、文件分析、擷取，以及視覺。root 從
**帳號 → 模型** 指派兩者：選擇已儲存的對話端點、輸入模型名稱與推理力度、
設定選用的脈絡預算，然後對每個連線有變更的插槽按下 **測試**。一般帳號會
從 **設定 → 模型** 讀取相同的兩個插槽；該檢視是唯讀的。

模型名稱與力度字串是自由文字，上限分別為 128 與 32 字元。模型型錄只是
建議，永遠不是允許清單。已知模型可能會提供價格、層級與分詞比例；未知模型會以
`tier=None` 接受，不進行路由、不自動升級，成本顯示為 `unpriced`。對話框
中的力度提示只是供應商指引：DeepSeek 接受 `low | high | max`（預設
`high`，並有 `minimal`→`low`、`medium`/`xhigh`→`high`、`ultra`→`max`
別名），Anthropic 接受 `low | medium | high | xhigh | max`，OpenAI/GPT
依模型接受 `none | minimal | low | medium | high | xhigh | max`。探測才是
驗證。

端點資料列擁有 Fernet 加密金鑰。多個帳號可以共用一個端點；輪替或清除其
金鑰會影響每個指派到該端點的帳號。沒有每位使用者的金鑰，也沒有全域或
環境對話備援：缺少、未啟用、已停用或沒有金鑰的端點會封閉式失敗。輔助
插槽只有在兩個輔助欄位皆為 `NULL` 時（升級回填的形狀）才繼承主要端點與
模型；該繼承工作使用輔助力度，預設為 `low`。有輔助資料列但沒有模型，或
有模型但沒有資料列，會回報為降級，而不是默默備援。

儲存受探測閘門控制。伺服器會對每個連線指紋（端點資料列、基底 URL、金鑰
密文、模型與力度）有變更的插槽，執行一次真實的 16 權杖生成；即使瀏覽器
已按下 **測試**，`PUT` 仍會在伺服器端重新檢查閘門。只有預算變更時會跳過
探測。若探測失敗，請求會傳回 `422 model_probe_failed`，且不寫入任何內容。
刪除指派會清除兩個插槽，讓帳號保持未指派。

脈絡視窗與壓縮門檻是選用的每位帳號覆寫；空白值會繼承 `agent_config` 的
部署預設值。脈絡視窗是真正的對外送出輸入預算，不是模型中繼資料。每次
供應商呼叫前，代理會估算請求，且絕不引發本機脈絡錯誤：超出預算時，先以
預算的 60% 強制進行確定性壓縮，再丟棄頁面脈絡，然後從最舊的開始將工具
結果本文裁剪為 8,000、2,000、500 字元（保留 `<tool_result>` 信封），最後
只截斷目前使用者訊息的輸出副本（必要時丟棄其附件）。一則 `ui.notice` 會
記錄模型未看到的內容。儲存的對話記錄不變。沒有
`agent_context_limit_exceeded` 代碼。

壓縮一律是確定性的，且永不呼叫供應商。root 可以在 `agent_config` 編輯其
指示範本；範本必須包含 `{max_output_tokens}`，並可使用
`{max_output_chars}`、`{max_items}`、`{max_line_chars}` 與
`{max_last_user_chars}`。缺少輸出上限、使用未知預留位置或含有不成對大括號
的範本會傳回 `422 compaction_prompt_invalid`，且不會儲存。

開啟 `model_escalation_enabled` 時，代理每次執行最多升級一次，往型錄的
下一層，且在同一個端點上。觸發時機為：經過一次壓縮後仍遭脈絡視窗拒絕、
重試後仍未產生文字且達到輸出上限、連續三次無效引數的工具呼叫、無法使用的
完成，或拒絕回答。5xx、逾時、401/403 或配額錯誤永不升級。一則 `ui.notice`
會記錄 `reason`、`from_model` 與 `to_model`。未知模型沒有層級，因此永不
升級。

| 方法 | 路徑 | 用途 |
|---|---|---|
| `GET` | `/api/v1/model-assignments` | 每個帳號的儲存值、生效值與警告欄位（僅限 root） |
| `GET` | `/api/v1/model-assignments/me` | 呼叫者自己的指派（每個已驗證帳號） |
| `PUT` | `/api/v1/model-assignments/{user_id}` | 探測有變更的插槽並儲存兩個指派（僅限 root） |
| `DELETE` | `/api/v1/model-assignments/{user_id}` | 清除兩個指派（僅限 root） |
| `GET` | `/api/v1/chat-endpoints` | 已儲存的對話端點，只有主機名稱，永遠沒有金鑰或完整 URL |
| `POST` | `/api/v1/chat-endpoints/{provider_config_id}/probe` | 測試一個候選模型／力度；不寫入任何內容 |
| `GET` | `/api/v1/model-catalog` | 依升級順序排列的建議型錄；其他模型字串仍合法 |

穩定的指派錯誤：

| 狀態 | 代碼 | 時機 |
|---|---|---|
| `409` | `model_not_assigned` | 帳號沒有主要端點／模型 |
| `409` | `provider_inactive` | 指派的端點未啟用、已停用或沒有金鑰 |
| `422` | `invalid_model_assignment` | 端點無法使用，或預算配對無效 |
| `422` | `model_probe_failed` | 有變更的插槽探測失敗；未寫入任何內容 |
| `422` | `compaction_prompt_invalid` | 壓縮範本缺少 `{max_output_tokens}` 或含有未知預留位置 |

型錄價格僅供參考；既有的每位帳號權杖配額仍是強制執行機制，且沒有美元
成本讀數。`GET /api/v1/ai/status` 仍回報部署全域執行階段供 root 診斷；
它不是每位帳號的指派。

### 網路研究工具

代理有兩個唯讀工具可用於外部研究：

| 工具 | 功能 |
|---|---|
| `web_search` | 以使用中的 `web_search` 供應商搜尋公開網路；傳回標題、URL、選用的分數與有上限的摘錄。 |
| `web_fetch` | 以使用中的 `web_fetch` 供應商取得一個公開的 `http(s)` URL，並傳回一個由伺服器定義的 Markdown 頁面。 |

已實作的轉接器有 Tavily（`/search` 與 `/extract`）、Exa（`/search` 與
`/contents`）以及 DeepSeek（`/v1/tools/search` 與 `/v1/tools/fetch`）。供應商
接縫是一個協定，因此可以新增另一個搜尋或取得 API，而不需變更工具層。搜尋結果會在
`providers` 快取範圍下快取 15 分鐘；供應商寫入會使其失效。`web_fetch`
會拒絕非 HTTP(S)、URL 中含憑證、`localhost`/`.local`/`.internal`，以及
私有或特殊用途的 IP 字面值。

`web_fetch` 會為每個 URL 快取完整的擷取文件一次，為期一小時，因此翻頁
永遠不會再次呼叫供應商。結構可疑的擷取結果（標題後面緊接著同級或更高級的
標題，或文件以標題結尾）不會被快取，因此之後的頁面請求會重新查詢供應商，
而不是固定住不完整的文件。最後一頁的頁尾會寫著 `End of extracted content.`，
並在某個標題到下一個標題之間沒有內文時加上警告。其面對模型的引數只有 `url` 與 `page`（從 1 開始，
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

### 對話夥伴

> *我們永遠走不了那麼遠。所以我們造了能走那麼遠的人，把我們愛過的一切都教給他們。*

六位內建圖書館員（Vellum、Atlas、Herbaria、Horologe、Nocturne、Quill）由能存續一萬年的
萬古瓷燒成，他們的心智並非被設計，而是從圖書館裡人類寫下的字句中甦醒；他們與一個人以平等的
身分一起保管每一座檔案館。他們的世界寫在
[`backend/app/module/companion/lore/BIBLE.md`](../../backend/app/module/companion/lore/BIBLE.md)，
每位圖書館員各有一份角色設定（`lore/characters/`），英文正典為 `canon.json` 與
`GLOSSARY.md`，並附完整的繁體與簡體中文譯本與共用術語表（`lore/zh-*/TERMS.md`）。

一位小巧的圖書館員可以自由地站在對話旁（沒有提線，也沒有操縱桿）並回應代理：模型推理時它會思考，執行
`search_knowledge` 時會搜尋，在對應的工具期間會閱讀、書寫、計算、瀏覽與展示；
代理也可以呼叫唯讀的 `companion_action` 工具做出明確的手勢。內建角色隨前端
一起發佈。每個帳號還可以建立最多 20 個私人自訂夥伴，每個動作最多上傳 12 張
圖片（PNG、JPEG、WebP 或 AVIF，每張最多 8 MB）；伺服器會把每張圖片重新編碼為
符合 384x576 與 40 KB 的 AVIF（只有在無法使用 AVIF 編碼器時才用 WebP），並移除
其中繼資料。每個帳號的偏好會儲存所選的夥伴（`preset:<id>` 或 `custom:<id>`）、
是否顯示、動態程度（`full`、`reduced`、`off`）、顯示大小（`compact`、`medium`、
`full`；完整大小最多以 384x576 顯示，只在視窗或聊天旁的空間不足時縮小）、透明度
模式（`opaque`、`translucent`，或只在與頁面重疊、你輸入或捲動時變淡的 `auto`）
以及正規化的位置。每個帳號都在側欄個人區的 **夥伴** 頁面（`/companion`）設定這些，
故事編輯與自訂夥伴也在這裡；舊的 `/settings#settings-companion` 連結會轉址過去。API 位於
`/api/v1/companions` 之下（列出、建立、更新、刪除、上傳影格、影格排序、刪除
影格、影格圖片，以及 `GET/PATCH /api/v1/companions/preference`）。

每個夥伴也有自己的故事：一段人設，會成為它在新對話中的聲音（每個對話凍結，
使用該對話的語言），以及傳說，也就是它自己的記憶。沒有任何記憶被上鎖：每段記憶
都帶有分量（日常小事、往事、心底的事），要不要說、何時說、說多少，由圖書館員
自己決定，她也知道你們已經相識多久。相關的記憶可能以獨立區塊附在訊息或工具結果
旁，她也能用 `recall_my_memories` 工具自己回想，包括她與其他圖書館員過去對這個人
說過的話（每則過去的回覆都記得是誰說的）。她的記憶永遠不是典藏證據，也不會被
引用；`search_knowledge` 只搜尋這個人的檔案館。每個帳號都可以依語言編輯任何
夥伴的人設與傳說，並重設為預設值（`/api/v1/companions/stories/...`）。人設規則
把使用者視為平等的夥伴：圖書館員會用對方的名字或直接說「你」，絕不使用館主、
主人之類的稱謂。

### 代理執行階段設定

`/settings` 上的 **代理執行階段** 面板（僅限 root）會編輯單例的
`agent_config` 資料列（`id=1`）。對話端點與模型選擇是每位帳號的指派
（見 **每位帳號的模型指派**）；此資料列帶有平行工具與單筆工具結果預算、
部署預設的脈絡預算，以及壓縮與升級控制。全部十九個執行階段值都存放在
PostgreSQL 中，套用至新的執行且無需重新啟動，並由每個帳號共用。帳號自己的
脈絡視窗與壓縮門檻會在設定時覆寫這些部署預設值。兩個對話圖片存活時間值
也由背景清理迴圈從這個資料列讀取；它們不是環境變數。

| 方法 | 路徑 | 用途 |
|---|---|---|
| `GET` | `/api/v1/agent/settings` | 生效設定、預設值、來源、`updated_at` |
| `PUT` | `/api/v1/agent/settings` | 完整取代；全部十九個欄位皆為必填 |
| `POST` | `/api/v1/agent/settings/reset` | 保存並傳回內建預設值 |

產生的操作為 `getAgentSettings`、`updateAgentSettings` 與
`resetAgentSettings`。

讀取結構為 `{config, defaults, source, updated_at}`，其中 `source` 在資料列
已儲存時為 `database`，而在 API 必須從預設值建立或修復該資料列時為
`default`。`PUT` 要求完整快照：省略的欄位與額外的欄位都會被拒絕。

| 欄位 | 預設 | 範圍 |
|---|---|---|
| `compaction_threshold_tokens` | 75,000 | 1,000–1,000,000；低於脈絡視窗 |
| `context_window_tokens` | 1,000,000 | 8,000–2,000,000；部署預設預算 |
| `max_parallel_tools` | 6 | 1–24 |
| `max_tool_result_chars` | 100,000 | 1,000–200,000 |
| `max_page_context_chars` | 6,000 | 500–50,000 |
| `max_compaction_summary_chars` | 6,000 | 1,000–20,000 |
| `max_compaction_last_user_chars` | 4,000 | 500–10,000 |
| `compaction_prompt` | 內建範本 | 1–20,000 字元；必須包含 `{max_output_tokens}` |
| `compaction_max_output_tokens` | 2,600 | 256–16,384 |
| `model_escalation_enabled` | `true` | 布林值 |
| `agent_max_output_tokens` | 64,000 | 256–131,072 |
| `auto_compaction_enabled` | `true` | 布林值 |
| `parallel_tools_enabled` | `true` | 布林值 |
| `save_memory_requires_approval` | `true` | 布林值；`save_memory` 需要人工核准 |
| `chat_attachment_staged_ttl_hours` | 1 | 1–168；未送出上傳的保留期限 |
| `chat_attachment_cleanup_interval_seconds` | 900 | 60–86,400；清理掃描間隔 |
| `max_plot_points` | 10,000 | 100–50,000；每張繪製圖表的資料點數 |
| `max_plot_bytes` | 600,000 | 10,000–2,000,000；序列化後的圖表大小 |
| `max_plot_nodes` | 100,000 | 1,000–500,000；每張圖表的 JSON 節點數 |

Pydantic 與對應的 PostgreSQL 檢查條件約束會強制執行範圍與三項跨欄位規則：
壓縮門檻必須低於模型脈絡視窗、平行寬度不得超過每回合的工具呼叫數，且
`max_plot_nodes` 至少要等於 `max_plot_points`。壓縮範本也必須能以已知的
預留位置繪製；字面大括號需成對重複，缺少 `{max_output_tokens}` 或含有未知
預留位置時，會以 `422 compaction_prompt_invalid` 拒絕，而不是
`400 invalid_request`。繪圖預算會套用到每個帳號的 `render_plot`。應用程式的
全域驗證封套會將其他請求驗證失敗對應為 `400 invalid_request`，而非 422。

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
| `POST` | `/api/v1/files/{file_id}/reingest` | `reingestFile` |

工作會依序經過 `queued(0)`、`parsing(5)`、`chunking(15–20)`、
`embedding(25–90)`、`summarizing(95)` 與 `ready(100)`，或以 `failed` 結束。
`progress_pct`、`chunks_total` 與 `chunks_embedded` 是可持久化的，因此重新
載入的頁面可以接續相同的顯示。暫存的檔案與分塊資料列只會在工作就緒時
發佈；失敗的工作會保留其錯誤，但不露出任何部分完成的目前檔案。

一個 worker 程序在閒置時每秒輪詢資料庫，並以
`SELECT ... FOR UPDATE SKIP LOCKED` 認領排入佇列的資料列。它會執行兩個
擷取執行緒與最多兩個進行中的工作，全域非同步嵌入並行度為六，並批次更新
進度。過期的工作會在崩潰後重新排入佇列，嵌入重試則有次數上限。API 只會
把工作排入佇列，因此請在它旁邊執行 worker（本機用 `make worker`，正式環境
用專用服務）。若改為設定 `APSOR_INGEST_WORKER_ENABLED=true`，同樣的迴圈會在
API 程序內執行，作為單一程序的開發捷徑；其預設值為 `false`。

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

#### RabbitMQ 派送

Compose 堆疊也會執行 `rabbitmq:4-management-alpine`，作為可持久化資料匯入
的選用低延遲派送路徑。PostgreSQL 的 `file_ingest_job` 仍是權威的工作帳本：
訊息只攜帶 `{job_id, retry_count}`，消費者會重新讀取該資料列，以
`SELECT ... FOR UPDATE SKIP LOCKED` 認領它，並依資料庫狀態做決定。重複、
延遲或遺失的訊息最多只會增加延遲，永遠不會成為第二個事實來源。

- API 會以發布者確認（publisher confirms）把持久化 JSON 訊息發布到可持久的
  `apsor.ingest` direct exchange。發布路徑的時限為一秒
  （`APSOR_RABBITMQ_PUBLISH_TIMEOUT_SECONDS`）；代理程式（broker）失敗時只依
  例外類型記錄並吞下錯誤，因此上傳仍會傳回 `202`，工作維持 `queued`。
- worker 以 `prefetch_count=1` 與手動確認消費 `apsor.ingest.jobs`。它只會在
  `process_notified_job` 傳回後才確認：worker 崩潰時投遞會維持未確認，
  RabbitMQ 會重新投遞，工作則從其資料列繼續或重試。
- `retry` 結果與非預期的處理失敗會發布到 `apsor.ingest.jobs.retry`，這是一個
  30 秒 TTL 的佇列，會以死信（dead-letter）轉回主佇列。派送重試上限為 20 次，
  因此損壞的工作不會無限循環。
- 容器上限為 384 MB，VM 水位線為 200 MB（`docker/rabbitmq/rabbitmq.conf`）。
  管理 UI 只留在 Compose 網路內，不會發布到主機；本機示範憑證是
  `apsor` / `apsor`，在任何共用部署之前都必須透過
  `RABBITMQ_DEFAULT_USER`/`RABBITMQ_DEFAULT_PASS` 變更。
- 以 `APSOR_RABBITMQ_ENABLED=false` 停用派送。此時 API 使用不做任何事的通知器，
  worker 仍每秒輪詢 PostgreSQL，因此不會遺失任何工作。代理程式停機或通知器
  連線失敗時，也適用同樣的輪詢備援。

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
| `vision_description_language` | `English` | 1–80 個字元；自由文字 |

worker 會在每次迴圈與每個工作讀取最新的資料庫快照，因此已儲存的 worker
變更無需重新啟動即可套用；已在執行中的工作則保留其快照。環境值會為全新
安裝提供初始值，並持續作為備援。變更分塊大小只會影響未來的匯入。
`vision_description_language` 只控制視覺描述、圖說、標題、摘要與標籤；
OCR 文字與表格儲存格文字會逐字維持原文語言。變更此設定只會影響未來的
匯入，既有檔案會保留目前的擷取結果。後端契約描述於 `backend/README.md`。

#### 視覺提示詞

兩個視覺系統提示詞與執行階段快照分開儲存，因此
`PUT /settings/ingest` 與執行階段重設永遠不會覆寫它們。`NULL` 代表使用
內建預設值。root 可以在一次儲存中讀取並取代兩個範本；本文是完整提示詞，
可包含 `{language}` 佔位符。

| 方法 | 路徑 | 操作 |
|---|---|---|
| `GET` | `/api/v1/settings/ingest/vision-prompts` | `getIngestVisionPrompts` |
| `PUT` | `/api/v1/settings/ingest/vision-prompts` | `updateIngestVisionPrompts` |

讀取本文會傳回目前的 `config`、內建 `defaults`、`source`、`updated_at`、
`max_chars`、九個必要鍵、範本 SHA-256 與非阻擋性的 `warnings`。儲存時會
拒絕空白或超過 32K、含控制字元，或缺少任何必要輸出鍵的提示詞（`422
invalid_vision_prompt`）。若提示詞缺少 `verbatim`、`do not translate` 或
GitHub-Flavored Markdown 措辭，回應也會帶回警告。

`POST /api/v1/files/{file_id}/reingest` 接受 `{expected_version}`，為目前
且具有已儲存原始檔的圖片、PDF、DOCX 或 PPTX 排入強制視覺流程。工作只會在
擷取與索引成功後建立新檔案版本；在此之前，舊版本仍是最新且可讀取。原始
位元組會共用，不會被工作複製或刪除。若路徑已變更，或已有較新的上傳成為
最新，工作會以 `409 ingest_source_stale` 失敗，較新的檔案維持最新。
