/**
 * System prompt editor strings (English source of truth).
 */
export const systemPrompt = {
  panel: {
    title: "System prompt",
    sectionCountOne: "{count} section",
    sectionCountOther: "{count} sections",
    loading: "Loading",
    unavailable: "Unavailable",
    collapse: "Collapse",
    expand: "Expand",
    collapseTitle: "Collapse system prompt",
    expandTitle: "Expand system prompt",
    sectionsAria: "System prompt sections",
    intro:
      "One ordered list: every section is editable, deletable, and reorderable. The list opens every new conversation as one provider system message, followed by the tool catalog and append-only messages. Existing conversations keep the prompt frozen when they were created.",
    order: {
      heading: "Provider request order",
      ariaLabel: "System prompt load order",
      promptTag: "prompt",
      userProfile: "User profile (if set)",
      toolCatalog: "Tool catalog",
      conversationMessages: "Conversation messages",
      hint:
        "Stable order: one system message → tools → append-only messages. The current time is appended to each user message when it is sent, so history is never rewritten.",
    },
    group: {
      eyebrow: "Prompt sections",
      title: "Ordered system prompt",
      lede:
        "Drag a grip to rewrite sort_order. The four seeded defaults are ordinary rows here.",
    },
    toolbar: {
      add: "Add section",
      reset: "Reset to defaults",
      hint: "Drag the grip, or focus it and press Space, then use the arrow keys.",
    },
    empty: {
      copy:
        "No sections. The provider receives only the tool catalog and conversation messages.",
      addFirst: "Add the first section",
    },
    error: {
      title: "System prompt sections did not answer.",
      retry: "Retry",
      retrying: "Retrying…",
    },
  },
  section: {
    charactersOne: "{count} character",
    charactersOther: "{count} characters",
    collapse: "Collapse",
    expand: "Expand",
    collapseTitle: "Collapse section",
    expandTitle: "Expand section",
    edit: "Edit",
    delete: "Delete",
    reorderAria: "Reorder {title}",
    reorderTitle: "Drag to reorder; press Space then use the arrow keys",
  },
  editor: {
    title: "Title",
    titlePlaceholder: "Archive voice",
    titleHelp: "Rendered as the Markdown heading of this section.",
    body: "Body",
    bodyPlaceholder: "Add persistent instructions for the archive agent.",
    count: "{count} / 32,000 characters",
    save: "Save section",
    saving: "Saving…",
    delete: "Delete",
    updated: "Updated {date}",
  },
  add: {
    eyebrow: "Settings · system prompt",
    title: "Add a system prompt section",
    description:
      "New sections are appended after the current last section. Drag them into place once saved.",
    cancel: "Cancel",
    submit: "Add section",
    submitting: "Adding…",
    titleLabel: "Title",
    titleHelp: "Up to 200 characters.",
    bodyLabel: "Body",
    bodyPlaceholder: "Add persistent instructions for the archive agent.",
    count: "{count} / 32,000 characters",
    titleRequired: "Title is required.",
    bodyRequired: "Body is required.",
  },
  delete: {
    eyebrow: "Settings · system prompt",
    title: "Delete this section?",
    description:
      "“{title}” will be removed from the ordered prompt. Existing conversations keep the prompt frozen at creation.",
    copy:
      "The remaining sections form the prompt for new conversations. This cannot be undone.",
    cancel: "Cancel",
    confirm: "Delete section",
    deleting: "Deleting…",
  },
  reset: {
    eyebrow: "Settings · system prompt",
    title: "Restore the four defaults?",
    description:
      "Every current section is removed and the four seeded defaults are inserted. Existing conversations keep their frozen prompt.",
    copy:
      "Identity, Instructions, Examples, and Context protocol are inserted as ordinary rows. They can be edited, deleted, or reordered afterwards.",
    cancel: "Cancel",
    confirmOne: "Replace {count} section with defaults",
    confirmOther: "Replace {count} sections with defaults",
    resetting: "Resetting…",
  },
  toast: {
    created: "System prompt section added.",
    saved: "System prompt section saved.",
    deleted: "System prompt section deleted.",
    reset: "System prompt reset to the four defaults.",
  },
};
