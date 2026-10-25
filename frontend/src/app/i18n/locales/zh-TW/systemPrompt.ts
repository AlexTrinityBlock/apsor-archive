/**
 * 系統提示詞編輯器字串（繁體中文）。
 */
export const systemPrompt = {
  panel: {
    title: "系統提示詞",
    sectionCountOne: "{count} 個區段",
    sectionCountOther: "{count} 個區段",
    loading: "載入中",
    unavailable: "無法使用",
    collapse: "收合",
    expand: "展開",
    collapseTitle: "收合系統提示詞",
    expandTitle: "展開系統提示詞",
    sectionsAria: "系統提示詞區段",
    intro:
      "一份有序清單：每個區段都能編輯、刪除與重新排序。清單會以單一 provider system message 開啟每個新對話，接著是工具目錄與 append-only 訊息。既有對話會保留建立時凍結的提示詞。",
    order: {
      heading: "Provider 請求順序",
      ariaLabel: "系統提示詞載入順序",
      promptTag: "提示詞",
      userProfile: "使用者個人檔案（若有設定）",
      toolCatalog: "工具目錄",
      conversationMessages: "對話訊息",
      hint:
        "順序固定：一個 system message → 工具 → append-only 訊息。目前時間會在送出時附加到每則使用者訊息後方，因此歷史永遠不會被改寫。",
    },
    group: {
      eyebrow: "提示詞區段",
      title: "有序系統提示詞",
      lede:
        "拖曳握把即可改寫 sort_order。四個預設值在這裡也是一般資料列。",
    },
    toolbar: {
      add: "新增區段",
      reset: "重設為預設值",
      hint: "拖曳握把，或聚焦後按 Space，再用方向鍵。",
    },
    empty: {
      copy:
        "目前沒有區段。Provider 只會收到工具目錄與對話訊息。",
      addFirst: "新增第一個區段",
    },
    error: {
      title: "系統提示詞區段沒有回應。",
      retry: "重試",
      retrying: "重試中…",
    },
  },
  section: {
    charactersOne: "{count} 個字元",
    charactersOther: "{count} 個字元",
    collapse: "收合",
    expand: "展開",
    collapseTitle: "收合區段",
    expandTitle: "展開區段",
    edit: "編輯",
    delete: "刪除",
    reorderAria: "重新排序 {title}",
    reorderTitle: "拖曳以重新排序；按 Space 後使用方向鍵",
  },
  editor: {
    title: "標題",
    titlePlaceholder: "檔案語氣",
    titleHelp: "會渲染成此區段的 Markdown 標題。",
    body: "內容",
    bodyPlaceholder: "為檔案代理加入長期指示。",
    count: "{count} / 32,000 字元",
    save: "儲存區段",
    saving: "儲存中…",
    delete: "刪除",
    updated: "更新於 {date}",
  },
  add: {
    eyebrow: "設定 · 系統提示詞",
    title: "新增系統提示詞區段",
    description:
      "新區段會附加在目前最後一個區段之後。儲存後可拖曳到想要的位置。",
    cancel: "取消",
    submit: "新增區段",
    submitting: "新增中…",
    titleLabel: "標題",
    titleHelp: "最多 200 個字元。",
    bodyLabel: "內容",
    bodyPlaceholder: "為檔案代理加入長期指示。",
    count: "{count} / 32,000 字元",
    titleRequired: "請輸入標題。",
    bodyRequired: "請輸入內容。",
  },
  delete: {
    eyebrow: "設定 · 系統提示詞",
    title: "刪除此區段？",
    description:
      "「{title}」會從有序提示詞中移除。既有對話會保留建立時凍結的提示詞。",
    copy: "剩餘區段會組成新對話的提示詞。此操作無法復原。",
    cancel: "取消",
    confirm: "刪除區段",
    deleting: "刪除中…",
  },
  reset: {
    eyebrow: "設定 · 系統提示詞",
    title: "恢復四個預設值？",
    description:
      "目前所有區段都會被移除，並插入四個預設區段。既有對話會保留凍結的提示詞。",
    copy:
      "Identity、Instructions、Examples 與 Context protocol 會以一般資料列插入；之後仍可編輯、刪除或重新排序。",
    cancel: "取消",
    confirmOne: "以預設值取代 {count} 個區段",
    confirmOther: "以預設值取代 {count} 個區段",
    resetting: "重設中…",
  },
  toast: {
    created: "已新增系統提示詞區段。",
    saved: "已儲存系統提示詞區段。",
    deleted: "已刪除系統提示詞區段。",
    reset: "系統提示詞已重設為四個預設值。",
  },
};
