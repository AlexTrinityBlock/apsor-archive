/**
 * 系统提示词编辑器字符串（简体中文）。
 */
export const systemPrompt = {
  panel: {
    title: "系统提示词",
    sectionCountOne: "{count} 个区段",
    sectionCountOther: "{count} 个区段",
    loading: "加载中",
    unavailable: "不可用",
    collapse: "收起",
    expand: "展开",
    collapseTitle: "收起系统提示词",
    expandTitle: "展开系统提示词",
    sectionsAria: "系统提示词区段",
    intro:
      "一份有序列表：每个区段都可以编辑、删除和重新排序。列表会以单一 provider system message 开启每个新对话，接着是工具目录和 append-only 消息。已有对话会保留创建时冻结的提示词。",
    order: {
      heading: "Provider 请求顺序",
      ariaLabel: "系统提示词加载顺序",
      promptTag: "提示词",
      userProfile: "用户个人档案（如有设置）",
      toolCatalog: "工具目录",
      conversationMessages: "对话消息",
      hint:
        "顺序固定：一个 system message → 工具 → append-only 消息。当前时间会在发送时附加到每条用户消息后面，因此历史永远不会被改写。",
    },
    group: {
      eyebrow: "提示词区段",
      title: "有序系统提示词",
      lede:
        "拖动握把即可改写 sort_order。四个默认值在这里也是普通数据行。",
    },
    toolbar: {
      add: "新增区段",
      reset: "重置为默认值",
      hint: "拖动握把，或聚焦后按 Space，再用方向键。",
    },
    empty: {
      copy: "目前没有区段。Provider 只会收到工具目录和对话消息。",
      addFirst: "新增第一个区段",
    },
    error: {
      title: "系统提示词区段没有响应。",
      retry: "重试",
      retrying: "重试中…",
    },
  },
  section: {
    charactersOne: "{count} 个字符",
    charactersOther: "{count} 个字符",
    collapse: "收起",
    expand: "展开",
    collapseTitle: "收起区段",
    expandTitle: "展开区段",
    edit: "编辑",
    delete: "删除",
    reorderAria: "重新排序 {title}",
    reorderTitle: "拖动以重新排序；按 Space 后使用方向键",
  },
  editor: {
    title: "标题",
    titlePlaceholder: "档案语气",
    titleHelp: "会渲染成此区段的 Markdown 标题。",
    body: "内容",
    bodyPlaceholder: "为档案代理加入长期指示。",
    count: "{count} / 32,000 字符",
    save: "保存区段",
    saving: "保存中…",
    delete: "删除",
    updated: "更新于 {date}",
  },
  add: {
    eyebrow: "设置 · 系统提示词",
    title: "新增系统提示词区段",
    description:
      "新区段会附加在当前最后一个区段之后。保存后可拖动到想要的位置。",
    cancel: "取消",
    submit: "新增区段",
    submitting: "新增中…",
    titleLabel: "标题",
    titleHelp: "最多 200 个字符。",
    bodyLabel: "内容",
    bodyPlaceholder: "为档案代理加入长期指示。",
    count: "{count} / 32,000 字符",
    titleRequired: "请输入标题。",
    bodyRequired: "请输入内容。",
  },
  delete: {
    eyebrow: "设置 · 系统提示词",
    title: "删除此区段？",
    description:
      "“{title}”会从有序提示词中移除。已有对话会保留创建时冻结的提示词。",
    copy: "剩余区段会组成新对话的提示词。此操作无法撤销。",
    cancel: "取消",
    confirm: "删除区段",
    deleting: "删除中…",
  },
  reset: {
    eyebrow: "设置 · 系统提示词",
    title: "恢复四个默认值？",
    description:
      "当前所有区段都会被移除，并插入四个默认区段。已有对话会保留冻结的提示词。",
    copy:
      "Identity、Instructions、Examples 和 Context protocol 会作为普通数据行插入；之后仍可编辑、删除或重新排序。",
    cancel: "取消",
    confirmOne: "用默认值替换 {count} 个区段",
    confirmOther: "用默认值替换 {count} 个区段",
    resetting: "重置中…",
  },
  toast: {
    created: "已新增系统提示词区段。",
    saved: "已保存系统提示词区段。",
    deleted: "已删除系统提示词区段。",
    reset: "系统提示词已重置为四个默认值。",
  },
};
