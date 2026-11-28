# 功能詳解

[English](../features.md) · **繁體中文** · [简体中文](../zh-CN/features.md)

這是一套以本機為優先的知識與記憶典藏，具備分支式檔案庫、線性記憶時間軸、
混合檢索（hybrid retrieval），以及有憑據的 AI 回答。每個帳號都有各自的私人
典藏；一個 root 帳號負責管理成員與共用的執行階段設定。

Apsor Archive 不是筆記清單。它是一個檢索介面，專為少量而刻意的工具呼叫而
設計：搜尋一個段落、讀取相鄰內容、沿路徑行走、取樣某個季節、壓製一則新
記憶，或追溯已被取代的記憶。每筆結果都帶著來源、分塊編號與時間。

> 狀態：v0.1.0 —— 檔案與記憶典藏、root 加上每位使用者各自的帳號、具備
> 資料庫後端執行階段限制的常駐 Pi 型代理、壓縮、平行工具、SSE 對話、
> 儲存問題的問答庫、可持久化的非同步資料匯入、專用的 PDF/DOCX/PPTX/試算表/圖片/
> 文字預覽引擎、資料夾工作區，以及三面板對話工作區。


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
- **代理限制以資料庫為後端。** 步驟與工具上限、平行寬度、結果預算與壓縮
  控制全都存放在單一經驗證的 `agent_config` 資料列中，並套用至新的執行，
  無需重新啟動。每個帳號的主要模型與脈絡預算是獨立的指派：脈絡視窗是
  真正的每位帳號輸入預算，不是模型中繼資料，且代理會在本機強制執行，
  而不是讓回合失敗。
- **對話模型依帳號指派。** root 會把每個帳號連結到已儲存的對話端點，
  以及供代理對話使用的自由文字模型與推理力度，並為摘要、記憶、匯入與
  視覺連結第二個端點。變更後的連線必須通過真實的供應商探測才能儲存。
  供應商資料列持有加密金鑰，因此輪替金鑰會影響指派到該端點的每個帳號。
- **長討論串可以摺疊或清除。** 壓縮會寫入摘要邊界；清除會從空的活動脈絡
  開始。兩種情況下完整對話記錄仍可閱讀。
- **記憶是線性且可追溯的。** 新的信念可以取代舊的。舊記憶會離開搜尋介面，
  但仍可沿其鏈結閱讀。
- **搜尋是混合式的。** 以 CJK 雙字組與拉丁詞元進行的 BM25，與向量召回
  並行。結果會去重並融合，同時記錄原因。過去的對話訊息也會以原始的
  256 字元視窗建立索引；另一條 cosine → BM25 → RRF 通道會傳回最佳的 15 個
  視窗，代理可以用穩定的訊息 ID 展開任何命中結果。
- **時間取樣忠實呈現。** 代理的時間軸工具每種事件種類最多傳回五個錨點，
  並精確回報略過多少事件。人類時間軸頁面則以 `complete=true` 取得所選視窗
  的完整事件，並在向下捲動時自動載入更早的視窗。
- **AI 回答有憑據。** 指派的對話模型收到的是檢索到的段落，不是整個
  檔案庫，且每項主張都必須附上引用。沒有可用的指派時，代理回合會以
  穩定代碼封閉式失敗。
- **問題的生命超越對話。** 可以在還沒有答案時先儲存問題，之後再提問，並把
  答案、引用、執行狀態與對話連結留在同一資料列上。編輯問題會清除過期
  答案，而不是在畫面上留下彼此不符的配對。
- **對話圖片是暫時的。** 貼到對話輸入區的螢幕截圖會立即上傳（逐張顯示
  位元組進度）到目前登入帳號的 `users/{user_id}/chat-temp/` 物件儲存區，
  經縮小與重新編碼後，列在可移除的暫存圖片管理器中。在所有選取的圖片都
  儲存完成前，無法送出。移除尚未送出的圖片或離開對話，會中止其上傳並立即
  丟棄暫存資料列；分頁關閉後遺留的暫存圖片，會在資料庫設定的存活時間（預設
  一小時）後過期。送出訊息時，會先把物件提升到 `users/{user_id}/chat-images/`
  再認領資料列，因此已送出的圖片會一直保留，直到擁有者刪除。供應商收到的是
  OpenAI 相容的 `image_url` 部分。刪除對話圖片會移除物件，並在對話記錄中
  留下如實的佔位說明。對話圖片不是典藏檔案，也無法被搜尋。
- **圖片存在於檔案庫中。** 圖片是普通的檔案紀錄，帶有原始位元組、路徑與
  分塊。支援視覺的對話供應商會加上 OCR、GitHub-Flavored Markdown 表格與
  完整的視覺描述；OCR 文字保留原文語言，描述語言與影像／文件提示詞範本
  則是僅限 root 的設定。每個視覺擷取的檔案會記錄實際送出提示詞的
  SHA-256、模式與描述語言。沒有這類供應商時，由檔名衍生的圖說仍讓本機
  上傳的內容可被搜尋。沒有另外的圖片索引。
- **視覺提示詞可完整編輯，但不做版本歷史。** root 可以取代完整的影像與
  掃描頁系統提示詞。儲存時只驗證九個輸出 JSON 鍵仍然存在；目前範本存放
  在 `ingest_config`。既有檔案會保留目前的擷取結果，直到明確重新匯入
  並建立新檔案版本。
- **文件會選擇自己的擷取器。** PDF 先嘗試文字，掃描頁面則退回視覺擷取。
  DOCX、PPTX、TXT、JSON、CSV 與日誌使用文字，並搭配 AI 結構化中介資料；
  圖片使用視覺或檔名備援。XLSX、XLS、XLSM 與
  ODS 活頁簿會逐工作表讀成 Markdown 表格，包含日期、數值、合併標題、隱藏
  工作表與公式備援；它們永遠不會進入視覺流程。
- **介面說三種語言。** 英文、繁體中文與簡體中文可在設定頁切換。選擇會依
  瀏覽器儲存，套用至整個介面，但絕不套用至典藏內容。
- **典藏是私人、多帳號且以本機為優先的。** 一個 root 帳號管理帳號與全域
  執行階段設定；其他每個帳號都獲得一份私人典藏，涵蓋檔案、資料夾、分塊、
  記憶、摘要、對話、項目、執行、核准、儲存的問題、提示詞與個人檔案卡片。
  PostgreSQL 資料列級安全性在每張私人資料表上強制執行擁有權，因此即使
  查詢少了篩選條件，也無法揭露他人的典藏。密碼使用 Argon2，工作階段使用
  HttpOnly cookie。請在自己的機器上執行；只有在你自己具備存取控制時，才
  將它放在 Cloudflare Tunnel 之後。
- **原始位元組存放在 S3 相容儲存中。** 預設是隨附的 RustFS 服務；也可以在
  設定精靈中改選 Cloudflare R2、任何 S3 端點或本機磁碟。讀取時遵循每筆資料列
  記錄的後端，因此分階段移轉期間可以服務混合的典藏。儲存桶一律保持私人，
  應用程式絕不發出預先簽署或公開 URL。

## 工具介面

典藏對外提供六個小型 HTTP 工具。每個 JSON 端點都對應代理可呼叫的一項檢索
或記憶操作；每個酬載都刻意小到足以讓 LLM 依序使用。

| 工具 | 端點 | 傳回內容 |
|---|---|---|
| `search_knowledge` | `GET /api/v1/search?query=&result_number=2` | 依典藏來源種類分別取 BM25 + 向量的前幾名結果，以 RRF 融合；另加最佳的 15 個過去對話視窗 |
| `read_file` | `GET /api/v1/files/{file_id}/chunks/{chunk}?chunk_range=1` | 從 1 開始算起的分塊視窗 |
| `read_timeline` | `GET /api/v1/timeline?year=&month=&day=&day_range=1` | 預設稀疏：每種事件種類最多五個取樣事件、密度與略過數量；`complete=true` 傳回整個視窗 |
| `read_path` | `GET /api/v1/paths?path=/history&path_depth=1&fuzzy_search=` | 目錄與檔案，或模糊路徑比對 |
| `save_memory` | `POST /api/v1/memories` | 一則帶有自動產生標題的新記憶、它所取代的已汰除記憶，以及任何新摘要；省略 `content` 即可汰除 `supersedes` ID 而不提供替代內容 |
| `read_memory` | `GET /api/v1/memories/{memory_id}?memory_range=1&trace_history=true` | 目標、相鄰項目、取代者、後繼者與鏈結 |

代理工具與 `/api/v1/tools/read_timeline` 一律使用稀疏預設；時間軸頁面會為
所選視窗加上 `complete=true`，並在向下捲動時自動載入上一個視窗。完整回應
回報 `mode="complete"`、`sampled == total == len(events)`、`skipped=0`、空的
`skips`，且每個事件的 `anchor=null`。頁面會將事件主軸排除在頁面脈絡之外，
因此完整清單不會成為代理的脈絡。

常駐典藏代理對模型提供十個工具：上述六個加上 `present_resource`、
`web_search`、`web_fetch` 與 `history_message`。HTTP 範例使用明確參數；HTTP 伺服器預設值為
`result_number=2`、`chunk_range=1`、`day_range=1`、`path_depth=1` 與
`memory_range=0`。文字會以約 4,000 字元、500 字元重疊的方式分塊；現有
檔案會保留其原始分塊邊界，直到重新匯入為止。過去的對話訊息使用另一種
固定視窗：256 字元、32 字元重疊（步幅 224）。代理的工具結構描述會選擇
自己的預設值，例如 `result_number=8` 與 `day_range=7`。`history_message`
接受 `<history_message>` 搜尋命中結果上顯示的 `id`，並傳回完整訊息加上
有上限的相鄰訊息。對於外部的 LLM
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
汰除）、`GET /api/v1/memories/{memory_id}/related` 與
`GET /api/v1/memories/related/files/{file_id}`（依已儲存的嵌入與關鍵字找出
關聯記憶；不呼叫供應商）、`POST /api/v1/summaries`、`GET /api/v1/stats`、
`GET /api/v1/health` 與 `GET /api/v1/ai/status`。`ai/status` 回報部署全域的
執行階段，供 root 診斷使用；它不是某個帳號的模型指派。

### 資料夾工作區

`/library` 是資料夾優先的工作區。麵包屑與資料夾側欄描述你所在的位置；主
區域會顯示目前路徑的資料夾卡片與檔案卡片。先前的表格仍以精簡清單檢視
提供，供密集瀏覽使用，需以 `view=list` 明確選取。

- **新增資料夾** 會建立要求的資料夾與任何缺少的祖先資料夾。此操作是
  冪等的：重複執行會傳回相同的資料夾與 `201`。
- **拖放上傳** 接受從桌面拖放到資料夾卡片或目前資料夾介面的檔案。上傳
  使用與上傳對話框相同的匯入路徑、副檔名允許清單與伺服器限制：每個上傳
  檔案 10 MB，以及 `.md`、`.markdown`、`.txt`、`.csv`、`.json`、`.jsonl`、
  `.toml`、`.ini`、`.env`、`.log`、`.pdf`、`.docx`、`.pptx`、`.xlsx`、
  `.xls`、`.xlsm`、`.ods`、`.jpg`、`.jpeg`、`.png` 或 `.webp`。對話框也
  支援 2 MB 的純文字建立。拖放的檔案永遠不會被開啟或執行。
- **剪貼簿貼上** 透過同一條匯入路徑上傳檔案。當剪貼簿中的名稱已存在於
  目標資料夾時，貼上的檔案會取得第一個可用的 ` (n)` 後綴（`image (1).png`），
  而不是默默成為新版本；一次貼上多個同名檔案時會依序編號。拖放或使用上傳
  對話框則維持明確的同名版本行為。
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
  `ui.notice` 項目。`model` 是標準的供應商訊息文字；連結的暫存圖片會在呼叫
  供應商時具體化為 `image_url` 部分，`data` 則僅供 UI／診斷使用。
- `agent_run` —— 單次提交的可持久化狀態（`request_id`、狀態、中止、最後
  項目、安全錯誤）。`agent_commit_seq` 會將同一交易中寫入的項目分組。
- `agent_approval` —— 針對需要確認的工具呼叫，保存一筆可持久化的
  待處理／已核准／已拒絕／已過期的人工決定，包含經驗證的引數、安全預覽，
  以及用來恢復等待中執行的迴圈快照。
- `agent_chat_attachment` —— 屬於單一帳號的對話圖片，包含物件儲存金鑰、
  經清理的中介資料，以及指向送出它們的使用者項目的選用連結。尚未送出的圖片
  位於 `users/{user_id}/chat-temp/`；送出時會提升到
  `users/{user_id}/chat-images/`。資料列採用軟刪除。
- `agent_config` —— 單例執行階段設定（`id=1`），保存經驗證的權杖、步驟、
  工具、頁面脈絡、壓縮與對話圖片存活時間限制。

使用者與助理項目也會以 `source_kind='history'` 複製到共用的扁平分塊索引中，
每個 256 字元視窗一列。背景的歷史索引器會回填既有對話、略過只有工具呼叫而
沒有內容的助理項目，並把軟刪除對話的視窗標記為非目前。代理會把每個命中結果
看成 `<history_message id="...">`，並呼叫 `history_message` 讀取完整的不可變
項目及其相鄰項目。

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
| `POST` | `/api/v1/agent/attachments` | 上傳一張暫存對話圖片（`multipart/form-data`，可選 `client_token`） |
| `POST` | `/api/v1/agent/attachments/cancel` | 依 `client_token` 冪等地丟棄暫存上傳（`204`） |
| `GET` | `/api/v1/agent/attachments?status=&limit=&offset=` | 列出帳號的暫存對話圖片 |
| `GET` | `/api/v1/agent/attachments/{attachment_id}/content` | 串流一張仍有效的暫存圖片 |
| `DELETE` | `/api/v1/agent/attachments/{attachment_id}` | 刪除物件並軟刪除其資料列（`204`） |
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
`{content, attachment_ids?, request_id?, page_context?, client_timezone?,
client_utc_offset_minutes?}`，而 `.../retry` 接受 `{request_id?}`。最多可以
附上四張已暫存的對話圖片；有圖片時文字可以留空。兩者預設都會串流
`text/event-stream`。用戶端時區會與伺服器呈現的 `<current_time>` 區塊一起
儲存在每個使用者項目上；該區塊會恰好附加在訊息文字之後一次。排序後的系統
提示詞區段會在建立對話時寫入，並凍結到該討論串中。四個預設值會以一般資料列
初始植入；設定頁讓 root 帳號能為整個部署編輯、刪除或重新排序每一個資料列。
事件名稱為 `run_start`、`message_start`、`message_delta`、`reasoning_delta`、
`message_end`、`tool_start`、`tool_end`、`approval_required`、`run_end` 與
`error`。`reasoning_delta` 攜帶在對應回答或工具呼叫之前抵達的供應商推理文字，
且永遠不會併入 `message_delta`。`run_start` 會回報 `page_context_entry_id`
（或 `null`）、`page_context_attached` 與 `resumed`，讓用戶端能標示是否寫入了
新快照，以及串流是否接續一筆可持久化的等待中執行。`tool_start` 與 `tool_end`
也會帶有助理呼叫批次的 `parallel`、`batch_size` 與 `parallel_index`。
`tool_end` 帶有已保存的工具結果 `data` 酬載，加上 `duration_ms` 與
`error_code`，因此檢視器可以在對話記錄重新取得完成前先呈現預覽。
`message_start` 的 `entry_id=null`，因為助理項目只會在 `message_end` 時保存；
增量僅供傳輸。供應商推理會作為有上限的顯示用遙測保存在助理項目中，並以純文字
`Thinking` 區塊呈現；它永遠不會進入供應商訊息、凍結的系統前綴或快取前綴雜湊。
確定性的壓縮摘要可能帶有一行有上限的 `Thinking:`。若想要取得完成的回合，請
改送 `Accept: application/json`。SSE 回應會設定
`Cache-Control: no-cache, no-transform` 與 `X-Accel-Buffering: no`，且
Starlette 的 GZip 中介軟體會排除 `text/event-stream`。

每個對話一次只允許一筆使用中的執行。預設值允許 6 個平行工具、自動壓縮前
75,000 個權杖的活動脈絡，以及每個工具 100,000 個結果字元。沒有步驟上限、
工具呼叫上限，也沒有累計的每回合權杖上限；回合只會在最終答案、使用者取消
或供應商失敗時結束。生效的脈絡視窗是部署預設值（1,000,000），除非帳號
指派了自己的預算；它是由本機溢位階梯強制執行的真實對外輸入預算，壓縮門檻
必須低於它。預算估算中，CJK 字元大約以每權杖 1.6 個字元計算，ASCII 文字則
維持模型目錄的比例，且目前脈絡區段中供應商回報的最大成功 `prompt_tokens`
會作為下限。因此僅供應商可見的狀態區塊中的 `context_used` 是保守估計，而非
與供應商完全一致的權杖數。每個結果都會依該單一結果上限獨立裁切，並附上可見
的 `[truncated]` 標記；沒有整回合的結果預算，也沒有第二次摘要呼叫。
100,000 字元的上限大約涵蓋二十五個 4,000 字元的分塊。這些是執行階段設定，
不是程式碼常數；請見上方的 **代理執行階段設定**。符合條件的工具呼叫會一起
開始，並在啟用平行工具時透過 `asyncio.gather` 執行。結果保存與 `tool_end` 的
順序遵循助理呼叫順序，而不是完成順序。停用平行工具時，執行會依序進行，且
事件會回報 `parallel=false`。

失敗或取消的執行可以重試，而不會重複使用者項目。當最新項目是失敗／取消
的助理回答、結尾的硬性上限工具結果（`step_limit`、`token_limit`、
`tool_call_limit` 或 `tool_result_budget_exhausted`），或最後一次串流在
記錄助理項目之前就失敗時，對話工作台與停駐的代理都會顯示「重試」動作。
重試會為同一個使用者項目啟動新的執行；UI 不會附加第二則訊息，並在串流
進行中停用該動作。若連溢位階梯都無法讓請求放得下，重試仍可能被供應商拒絕。
當最近一次執行已完成或並非失敗／取消時，端點會傳回
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

當 `auto_compaction_enabled` 為 true，且估計的活動脈絡超過
`compaction_threshold_tokens` 時，系統會在下一次呼叫供應商前附加一個
`pi.compaction` 項目。這項檢查會在新使用者回合之前執行，也會在執行中的
回合因工具或頁面脈絡而成長後再次執行，因此脈絡塞滿時會壓縮，而不是讓
供應商呼叫失敗：

- 該項目會將 `head_entry_id` 設為自己的 ID，因此較舊的項目維持不可變，
  但會落在新的活動脈絡之外。
- 其供應商訊息以 `<compaction>` 開頭，並帶有 `<last_user_input>`（壓縮前
  的最後使用者輸入）與 `<summary>`。
- 同一筆交易會依序寫入壓縮 → 頁面脈絡（當頁面重新附加時）→ 使用者，
  因此模型會在新的請求之前看到摘要。

這會開始新的 KV 快取系譜。系統提示詞與工具快照維持凍結，舊的對話記錄
仍可在 `/chat` 與浮動面板中閱讀。

壓縮一律是確定性的：永不呼叫供應商。摘要受 `compaction_max_output_tokens`
（預設 2,600）限制，並由 root 可編輯的 `compaction_prompt` 渲染；範本必須
包含 `{max_output_tokens}`，舊的字元上限仍然適用。溢位階梯也可以為單一
對外請求建立臨時壓縮，而不附加邊界。

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
搜尋、儀表板；記憶是檔案庫的「記憶」分頁），接著是包含 **使用者個人檔案** 的個人區塊，然後是
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

對話檢視器、檔案庫工作區與資料夾看板已在目前版本中實作。正式用戶端會
在 Docker 映像檔內從 `frontend/` 編譯，因此變更前端後只需重新建置映像檔。

### 資源預覽

檔案會在檔案庫內的現地預覽彈出視窗中開啟；記憶位於檔案庫的「記憶」分頁，
閱讀器在 `/library/memories/:id`，並有一個依已儲存的嵌入、共同關鍵字與共同
摘要排序的「關聯記憶」區段。舊版的 `/memory/*` 與 `/viewer/*` URL 會重新導向
至那些介面，因此舊引用與書籤仍可運作。

| 資源 | 渲染器 |
|---|---|
| PDF | `react-pdf` 11 + 內附的 `pdfjs-dist` 6、頁面導覽、縮放、符合寬度、文字層 |
| DOCX | `docx-preview`，位於停用指令碼的沙箱中 |
| PPTX | `pptxviewjs` Canvas 渲染器，支援投影片導覽與鍵盤方向鍵 |
| 試算表（XLSX/XLS/XLSM/ODS） | 延遲載入的 SheetJS 網格、工作表分頁、隱藏標記、凍結表頭，以及 500 × 50 的受限預覽 |
| 圖片 | 使用標準檔案內容端點的原生圖片 |
| 文字／JSON／Markdown／CSV | 典藏頁面，支援換行／複製／下載、美化 JSON、GFM Markdown |
| 記憶 | 壓製紀錄的記憶葉片，附系譜與追溯連結 |

`GET /api/v1/files/{file_id}/content` 會以 `nosniff`、沙箱化 CSP、
ETag/Last-Modified 與單一範圍 HTTP Range 支援（`206`/`416`；
`If-None-Match` 傳回 `304`）行內提供原始檔。`/download` 仍為附件。
舊的純文字紀錄的 `has_original=false`；這類頁面會完全略過 `/content` 探查，
並讀取已索引的分塊。

每個上傳的圖片、PDF，以及內嵌預覽圖的 Office 檔案，也會在匯入時產生一張
極小的 WebP 縮圖（`GET /api/v1/files/{file_id}/thumbnail`）。檔案庫卡片、
媒體格線、對話資源卡片與預覽載入狀態，都會先在依已知尺寸預留的方框內畫出
縮圖，因此完整預覽載入時不會跳動或閃爍。資料匯入 worker 會為較早上傳的檔案
回填縮圖（`APSOR_THUMBNAIL_BACKFILL_ENABLED`，預設開啟）。

PDF.js 的 CMaps 與標準字型會由 `bun run pdf-assets` 從固定版本的
`pdfjs-dist` 套件複製到 `frontend/public/pdfjs/`，`dev` 與 `build` 會
自動執行此動作。Vite 會在建置映像檔時將它們輸出到 `frontend/dist/pdfjs/`，
因此會與其餘產物一起打包。它們會在本機提供，且永遠不會從 CDN 取得。

### 帳號、角色與工作階段

第一次造訪時，應用程式會要求你建立 root 帳號。沒有預設密碼，也沒有電子
郵件復原。root 接著可以從 **帳號** 建立一般帳號；新帳號會以產生的 20
字元臨時密碼建立，該密碼只顯示一次，且帳號必須在任何典藏內容載入之前
選擇新密碼。新帳號也會繼承部署的主要對話端點與模型，因此對話與背景 AI
可立即使用；若部署沒有使用中的對話端點，帳號會保持未指派。root 可以停用、啟用、重設及模擬其他帳號。停用帳號或重設其
密碼會撤銷其工作階段；撤銷會在請求開始時檢查，因此已經在串流的 SSE
回合可能會完成目前的執行。帳號永遠不會被刪除，因此使用者名稱會一直
保留。

**帳號** 現在使用較大的資訊卡片。每張卡片帶有頭像、名稱與 `@username`、
角色／狀態標籤、建立日期、上次登入，以及該帳號彙總的代理用量：總計、
提示、完成與快取權杖、API 呼叫、回合與最後活動。提示／完成的劃分會以
小型長條圖呈現，而沒有代理活動的帳號仍會顯示可讀的零狀態。用量會依每次
代理執行計數，並由資料庫觸發程序彙總，因此卡片仍只是低成本的 root 專用
清單讀取，而不是跨帳號的對話掃描。

每張卡片也會彙總該帳號的模型指派。root 會在權杖配額旁開啟 **模型**，指派
主要與輔助端點、其自由文字模型與力度，以及選用的脈絡預算，或重設兩個
插槽。帳號本身會在 **設定 → 模型** 以唯讀方式看到相同的兩個插槽；只有
root 可以變更它們。

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
**常用提示詞**、**模型** 與 **語言**，而 root 會看到全部九個分頁。儀表板
與統計計數的範圍限於登入的帳號；AI 狀態是部署全域的執行階段診斷，而不是
帳號的模型指派。密碼會以 Argon2
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
  擷取：原文語言的 OCR 文字、GitHub-Flavored Markdown 表格，以及以設定的
  描述語言撰寫的完整視覺描述。否則使用由檔名衍生的圖說，並設定
  `extraction_method=filename`。圖片仍是普通的檔案庫檔案。
- **PDF** —— 先使用 pypdf 文字；當文字為空、亂碼，或 AI 結構化分析指出
  `use_vision` 時，以 pypdfium2 呈現最多 10 頁並執行文件頁模式視覺擷取：
  OCR、表格與簡短版面說明。
- **DOCX** —— python-docx 段落與表格；內嵌圖片可提供視覺備援，並使用完整
  影像模式的描述與表格。
- **PPTX** —— python-pptx 投影片文字框、表格、群組圖形與講者備忘稿；內嵌的
  `ppt/media` 圖片可提供視覺備援，並使用完整影像模式的描述與表格。不支援舊版
  二進位 `.ppt`。
- **XLSX / XLS / XLSM / ODS** —— python-calamine 依序讀取工作表，包含隱藏
  工作表與合併儲存格，並把每個工作表渲染成 GitHub-Flavored Markdown 表格。
  優先使用公式快取值；對於 OOXML 活頁簿，openpyxl 會在產生的檔案沒有快取
  結果時補回公式文字。上限為每工作表 10,000 列、100 欄、每儲存格 4,000
  字元，以及會依 500 分塊上限自動下調的活頁簿文字預算；截斷會留下明確標記。
  試算表擷取只使用文字，永不使用視覺流程。

每個視覺擷取的檔案會記錄 `vision_prompt_sha256`、`vision_prompt_mode`
（`image` 或 `document`）與 `vision_description_language`；舊資料列維持
`null`，代表未記錄提示詞。自訂提示詞只會套用至未來的匯入。若要從已儲存的
原始檔建立新版本，請使用上方的重新匯入路由；文字檔不符合資格，而沒有內嵌
圖片的 DOCX 或 PPTX 會維持純文字結果，不記錄提示詞指紋。

相同的匯入也可以透過 `POST /api/v1/files/async` 與
`POST /api/v1/files/text/async` 非同步使用；請輪詢
`GET /api/v1/files/ingest-jobs/{id}` 取得階段與分塊進度。請見上方的
**資料匯入執行階段**。

互動式文件：<http://127.0.0.1:8000/api/docs>。OpenAPI 結構描述是已提交
Orval 用戶端的來源。
