# 安全性與隱私

[English](../security.md) · **繁體中文** · [简体中文](../zh-CN/security.md)

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
- 正式 Compose 檔案不發佈任何主機連接埠；Cloudflare Tunnel 連到 Caddy，
  Caddy 再連到 API。登入節流是記憶體內實作，因此僅限單一程序；請執行一個
  API 程序，或在擴充前將節流移至 Valkey。
- 路徑會拒絕穿越區段、反斜線、控制字元與過長的值。上傳上限為 10 MB，
  且僅限於副檔名允許清單。
- 來自檔案與記憶的 HTML 會透過 React 以文字呈現。代理 Markdown 使用
  `skipHtml`；DOCX 預覽會在停用指令碼的沙箱中執行，PPTX 投影片則繪製到本機
canvas。UI 永遠不會使用
  `dangerouslySetInnerHTML`。
- DeepSeek 金鑰位於 `.secrets/deepseek.env` 或環境中。它永遠不會被
  記錄、傳回或提交。從設定頁儲存的金鑰會在 PostgreSQL 中加密，且只會
  以四字元提示傳回。
- 物件儲存憑證位於已列入 gitignore 的 `.secrets/r2.env` 或 `.secrets/s3.env`
  （隨附的 RustFS 另有 `secrets/` 下的 Docker secret 檔案），以唯讀方式掛載，
  且永遠不會成為容器環境變數。儲存桶是私人的，沒有預先簽署或公開 URL。
- AI 呼叫會發生在摘要與代理回合。若供應商失敗，API 會傳回穩定的錯誤，
  而不是編造答案。
