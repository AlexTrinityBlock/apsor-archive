/**
 * Memory workspace strings (English source of truth): the memory vault, the
 * pressing room, the reader, saved questions, and the user profile.
 */
export const memory = {
  common: {
    crystal: "MEMORY #{id}",
    untitledMemory: "Untitled memory",
    breadcrumbAria: "Breadcrumb",
    copyMemory: "Copy memory",
    copyMemoryTitle: "Copy the memory text",
    cancel: "Cancel",
    occurred: "Occurred",
    pressed: "Pressed",
    source: "Source",
    recordId: "Record id",
    notReported: "not reported",
    sourceValue: "source: {source}",
    reason: "Reason: {reason}",
    genericError: "The archive could not complete that request.",
  },
  status: {
    active: "Active tip",
    deprecated: "Deprecated",
    filterAria: "Filter memories by status",
    filterAll: "All",
    filterActive: "Active",
    filterDeprecated: "Deprecated",
    nounActive: "active",
    nounDeprecated: "deprecated",
    nounMatching: "matching",
  },
  vault: {
    eyebrow: "Memory · vault",
    title: "Memory Vault",
    description:
      "Every pressed memory, newest occurrence first. Active memories stay in search and the timeline; deprecated memories remain readable with their lineage.",
    activeLabel: "active",
    deprecatedLabel: "deprecated",
    pressMemory: "Press memory",
    searchLabel: "Search memories",
    searchPlaceholder: "Search memories by phrase or keyword…",
    clearSearchAria: "Clear memory search",
    shownLoadedTotal:
      "{visible} shown · {loaded} loaded · {total} total",
    searchingMemories: "Searching memories…",
    readingMemories: "Reading memories…",
    searchMatchesCount: "{visible} of {loaded} memory matches",
    searchModeTextVector: "Text + vector search",
    searchModeNewest: "Newest occurrence first",
    textCandidatesTitle: "Selected text candidates across all result kinds",
    vectorCandidatesTitle: "Selected vector candidates across all result kinds",
    mergedCandidatesTitle:
      "Deduplicated union of text and vector candidates",
    serverDurationTitle: "Server search duration",
    diagnosticText: "text",
    diagnosticVector: "vector",
    diagnosticMerged: "merged",
    filterNoteSearch:
      "The status filter applies to the {count} memory matches returned by this search.",
    filterNoteLoaded:
      "The status filter applies to the {count} loaded records.",
    filterNoteLoadedMore:
      "The status filter applies to the {count} loaded records; load older records to widen the scan.",
    searchNote:
      "Search is capped at {limit} memory matches and ranked by fused text and vector score. Refine the phrase to narrow the set.",
    searchSkeleton: "Searching the vault",
    searchErrorTitle: "The vault search did not answer.",
    searchErrorDescription:
      "The memory search request failed before any results were returned.",
    noMatchEyebrow: "No match",
    noMatchTitle: "No memory answers this phrase.",
    noMatchDescription:
      "Search returned no memory matches for “{query}”. Try a broader phrase, or search the whole archive for related files and summaries.",
    clearSearch: "Clear search",
    searchWholeArchive: "Search the whole archive",
    filteredEyebrow: "Filtered out",
    filteredSearchTitle: "No {status} memories in these matches.",
    filteredBrowseTitle: "No {status} memories in the loaded records.",
    filteredSearchDescription:
      "The search returned matches, but none have the selected status. Clear the status filter to see every match.",
    filteredBrowseMoreDescription:
      "The status filter only scans records already loaded. Load older records below, or clear the filter.",
    filteredBrowseEndDescription:
      "Every loaded record has a different status. Clear the filter to see the full vault.",
    showAllStatuses: "Show all statuses",
    browseSkeleton: "Reading the memory vault",
    browseErrorTitle: "The vault did not answer.",
    browseErrorDescription:
      "The memory list request failed before any records were returned.",
    emptyEyebrow: "Empty vault",
    emptyTitle: "No memories have been pressed yet.",
    emptyDescription:
      "A memory records a decision, an observation, or a change of mind. Press the first memory to open the vault.",
    pressFirstMemory: "Press the first memory",
    loadMoreError: "The next page of memories did not load.",
    retryOlderRecords: "Retry older records",
    loadedOfTotal: "{loaded} of {total} records loaded",
    loadingOlder: "Loading older records…",
    loadOlder: "Load older memories",
    endOfVault: "End of the vault · {count} memories read",
  },
  card: {
    matchedBy: "matched by {by}",
    fusedScoreTitle: "Fused text and vector rank score returned by search",
    fusedScore: "fused {score}",
    pressedAt: "pressed {date}",
    edit: "Edit",
    deprecate: "Deprecate",
    readRecord: "Read record",
    supersededByPrefix: "Superseded by ",
    supersededBySuffix: ". Kept in the ledger; no longer retrieved.",
    deprecatedDirectly:
      "Deprecated directly and kept in the ledger for provenance.",
    replacesPrefix: "Replaces ",
    replacesSuffix: ".",
  },
  states: {
    readingMemories: "Reading memories",
    readInterrupted: "Read interrupted",
    retry: "Retry",
    didNotAnswer: "The archive did not answer.",
  },
  newView: {
    breadcrumbCurrent: "Pressing room",
    eyebrow: "Memory · pressing room",
    title: "Press a new memory.",
    description:
      "A new memory records an occurrence and may supersede earlier beliefs. The older entries become deprecated, not deleted: they leave default search and the timeline, yet the lineage remains readable.",
    metaNewRecord: "new record",
    metaSupersedesOne: "supersedes {count} record",
    metaSupersedesOther: "supersedes {count} records",
    backToVault: "Back to vault",
    formEyebrow: "New record",
    formTitle: "What should be remembered?",
    contentLabel: "Content",
    contentHint: "required · 8,000 characters max",
    contentPlaceholder:
      "A decision, a change of mind, an observation, a moment that should survive.",
    contentHelp: "Plain text; stored and indexed exactly as written.",
    contentCount: "{count} / 8,000",
    contentRequired:
      "Write the memory before pressing it into the archive.",
    contentTooLong: "A memory is limited to 8,000 characters.",
    occurredLabel: "Occurred at",
    occurredHint: "optional · defaults to now",
    occurredInvalid: "The occurred-at time is not a valid date.",
    supersedesLabel: "Supersedes",
    supersedesHint: "optional · comma-separated ids",
    supersedesPlaceholder: "12, 14",
    supersedesHelp:
      "Numeric memory ids only. Up to 50 records can be replaced.",
    supersedesInvalidFormat:
      "Use comma-separated numeric memory ids, for example 12, 14.",
    supersedesPositive: "Memory ids must be positive integers.",
    supersedesLimit:
      "A memory can supersede at most 50 earlier memories.",
    save: "Save memory",
    saving: "Pressing the memory…",
    saveFailed: "Could not save the memory. {detail}",
    savedToast: "Memory {id} saved.",
    savedToastWithDeprecatedOne:
      "Memory {id} saved; 1 earlier memory is now deprecated.",
    savedToastWithDeprecatedOther:
      "Memory {id} saved; {count} earlier memories are now deprecated.",
    sourceNoteBefore: "The record is saved with source ",
    sourceNoteAfter:
      ". If the API returns an auto-created summary, it appears in the receipt on the saved record.",
    consequencesEyebrow: "Consequences",
    consequencesTitle: "What saving does",
    step1Before: "The new memory becomes ",
    step1Strong: "active",
    step1After: " with a fresh id and its occurred-at time.",
    step2Before: "Every listed memory becomes ",
    step2Strong: "deprecated",
    step2After: " and points to the new record as its successor.",
    step3:
      "Deprecated memories leave default search and the default timeline. Their chunks stop being retrieved; their text remains readable with the full chain.",
    step4:
      "If enough unsummarized memories have accumulated, the response may include an auto-created summary.",
    deprecationsEyebrow: "Will be deprecated",
    deprecationsTitle: "Listed earlier memories",
    deprecationsNote:
      "These ids will be deprecated if they exist and are still active. The backend rejects an id that is already deprecated.",
    deprecationsEmpty:
      "No earlier memories are listed. This save will not deprecate anything.",
  },
  reader: {
    eyebrow: "Memory · reader",
    description:
      "One pressed memory with its direct lineage, its temporal neighbours, and the full supersession chain. Deprecated memories remain readable after they leave search and the timeline.",
    readingRecord: "Reading record",
    editText: "Edit text",
    deprecate: "Deprecate",
    backToVault: "Back to vault",
    skeleton: "Reading the memory trace",
    errorTitle: "The memory trace did not answer.",
    errorDescription:
      "The record could not be read. Retry, or return to the vault and choose another memory.",
    saveReceipt: {
      eyebrow: "Just pressed",
      title: "Memory saved",
      noDeprecated:
        "No earlier memory was deprecated by this save. The new record is active.",
      deprecatedOne:
        "1 earlier memory was marked deprecated. The records remain readable and stay in the supersession chain.",
      deprecatedOther:
        "{count} earlier memories were marked deprecated. The records remain readable and stay in the supersession chain.",
      autoSummary: "Auto-created summary",
      model: "Model",
      memories: "Memories",
      period: "Period",
    },
    record: {
      deprecatedNote:
        "This memory is deprecated. It left default search and the timeline, but remains readable here.",
      readSuccessor: "Read successor MEMORY #{id}",
      retiredDirectly:
        "It was retired directly; no successor replaced it.",
    },
    lineage: {
      eyebrow: "Direct lineage",
      title: "What this memory replaces",
      supersedesHeading: "This memory supersedes",
      supersedesEmpty: "No earlier memories are listed on this record.",
      supersededByHeading: "Superseded by",
      retiredEmpty:
        "This memory was retired directly. No later record replaced it.",
      currentEmpty:
        "Nothing has replaced this memory. It remains the current leaf in its chain.",
    },
    neighbours: {
      eyebrow: "Adjacent in occurrence order",
      title: "Neighbouring memories",
      before: "Before",
      after: "After",
      earliest: "This is the earliest memory in the archive.",
      latest: "This is the latest memory in the archive.",
    },
    chain: {
      eyebrow: "Full chain",
      title: "Supersession history",
      empty:
        "No supersession links are recorded for this memory. It stands alone in the chain.",
      capped:
        "The API returns at most 20 linked records; this chain is at that cap.",
      order:
        "Oldest at the top. Each step moves toward the current memory, including deprecated leaves.",
    },
    supersede: {
      disabledTitle: "This memory is already deprecated.",
      action: "Supersede this memory",
    },
  },
  editDialog: {
    eyebrow: "Memory · edit",
    title: "Edit memory text",
    description:
      "MEMORY #{id}. The title is regenerated from the new text; the record keeps its id and occurrence time.",
    label: "Memory text",
    count: "{count} / 8,000 characters",
    emptyError: "Memory text cannot be empty.",
    save: "Save memory",
    saving: "Saving…",
    updated: "Memory #{id} updated.",
  },
  deprecateDialog: {
    eyebrow: "Memory · deprecate",
    title: "Retire this memory?",
    description:
      "MEMORY #{id} keeps its text and stays readable, but leaves default search and the timeline. No replacement memory is written.",
    reasonLabel: "Reason (optional)",
    reasonPlaceholder:
      "For example: already bought, cancelled, or no longer true.",
    reasonHelp: "Stored on the deprecated record for later provenance.",
    action: "Deprecate memory",
    saving: "Deprecating…",
    updated: "Memory #{id} deprecated.",
  },
  missing: {
    breadcrumbCurrent: "Record not found",
    eyebrow: "Memory · record not found",
    title: "Memory not found.",
    invalidDescription:
      "The route did not contain a numeric memory id. Memories are addressed by their stable integer id, not by a title.",
    missingDescription:
      "Memory {id} is not in the archive. It may have been removed, or the id may never have existed.",
    missingDescriptionFallback:
      "The memory on this route is not in the archive. It may have been removed, or the id may never have existed.",
    backToVault: "Back to vault",
    emptyEyebrow: "No memory at this address",
    emptyTitle: "This memory is not in the archive.",
    emptyDescription:
      "Deprecated memories remain readable, so a missing record means it is genuinely absent rather than merely retired. Return to the vault to browse the surviving lineage.",
    browseVault: "Browse the vault",
    pressNew: "Press a new memory",
  },
  questions: {
    eyebrow: "Questions · saved shelf",
    title: "The inquiry shelf.",
    description:
      "Keep a question before you have an answer. Run it in Chat when you are ready; the answer, its citations, and the conversation return here.",
    metaLoadedSaved: "{loaded} loaded · {total} saved",
    metaReading: "Reading shelf",
    shelfControlsAria: "Shelf controls",
    filterAria: "Filter by status",
    statusAll: "All",
    statusAnswered: "Answered",
    statusRunning: "Running",
    statusFailed: "Failed",
    statusCancelled: "Cancelled",
    statusNotAsked: "Not asked",
    countOnPageTitle: "Count on the loaded page",
    textFilterLabel: "Filter loaded questions by text",
    textFilterPlaceholder: "Filter this page…",
    clearTextFilterAria: "Clear text filter",
    saveQuestion: "Save question",
    toolbarNoPage: "Reading the loaded page",
    toolbarPage:
      "Page {page} of {totalPages} · {loaded} loaded of {total} saved · status counts and text filter cover only the loaded page",
    toolbarMatchOne: " · {count} match",
    toolbarMatchOther: " · {count} matches",
    aiNoticeTitle: "AI provider not configured.",
    aiNoticeBody:
      "Answers cannot be generated until a provider is saved.",
    openSettings: "Open Settings",
    dismissProviderNotice: "Dismiss provider notice",
    refreshFailed: "The shelf could not refresh. {detail}",
    loadingAria: "Reading saved questions",
    loadErrorEyebrow: "Reading interrupted",
    loadErrorTitle: "The shelf did not answer.",
    retry: "Retry",
    retrying: "Retrying…",
    emptyEyebrow: "Blank pages",
    emptyTitle: "No saved questions yet.",
    emptyDescription:
      "Write a question and keep it here until you are ready to ask it. Answers, citations, and their conversation stay beside it.",
    pastPageEyebrow: "Past the last page",
    pastPageTitle: "This page of the shelf is empty.",
    pastPageDescription:
      "The shelf changed while this page was open. Return to the newest entries to continue reading.",
    backToFirstPage: "Back to the first page",
    filteredEyebrow: "No matches on this page",
    filteredTitle: "Nothing matches these filters.",
    filteredDescription:
      "Status tabs and the text filter only cover the questions loaded on this page. Clear the filters to see the rest of the page.",
    clearFilters: "Clear filters",
    paginationAria: "Saved question pages",
    previous: "Previous",
    next: "Next",
    pageOf:
      "Page {page} of {totalPages} · {start}–{end} of {total}",
    card: {
      folio: "FOLIO Q-{number}",
      answer: "Answer",
      runInProgress: "Run in progress",
      runInProgressDescription:
        "The agent is still working on this question. The shelf refreshes while a run is active.",
      runFailed: "Run failed",
      runCancelled: "Run cancelled",
      runFailedFallback:
        "The agent did not return a readable error detail.",
      runCancelledFallback:
        "The run was cancelled before the agent returned an answer.",
      answerFailed: "The run failed before an answer was recorded.",
      answerCancelled:
        "The run was cancelled before an answer was recorded.",
      answerRunning: "The agent is still working on this question.",
      answerNotAsked:
        "Not asked yet. Run this question in Chat to record an answer.",
      asking: "Asking…",
      running: "Running…",
      retry: "Retry",
      runInChat: "Run in Chat",
      askingLoader: "Asking the archive",
      askingMessage:
        "Asking the archive. This can take several seconds.",
      askedLabel: "Asked",
      savedLabel: "Saved",
      updatedLabel: "Updated",
      conversation: "Conversation #{id}",
      edit: "Edit",
      delete: "Delete",
      deleteConfirmAria: "Confirm deleting this question",
      deleteConfirm: "Delete?",
      deleting: "Deleting…",
      cancel: "Cancel",
    },
    dialog: {
      createEyebrow: "Save question",
      editEyebrow: "Edit question",
      createTitle: "Keep a question for later.",
      editTitle: "Revise this question.",
      closeAria: "Close dialog",
      questionLabel: "Question",
      placeholder: "What should the archive answer later?",
      createDescription:
        "Saving stores the question only; no answer is generated until you run it in Chat.",
      editDescription:
        "Saving changed text clears the stored answer and conversation link.",
      cancel: "Cancel",
      save: "Save question",
      saveChanges: "Save changes",
      saving: "Saving…",
    },
    citations: {
      unrecognised: "Unrecognised citation token",
      openFile: "Open {label} in the file library",
      openMemory: "Open {label} in the memory vault",
      expandSummary: "Expand this summary citation",
      summaryBody:
        "Summaries are cited inline in this build and have no standalone page.",
      mediaTitle:
        "Media is part of the file library and has no separate citation route.",
      label: "Citations",
    },
    toast: {
      saved: "Question saved to the shelf.",
      updated: "Question updated.",
      updatedAnswerCleared:
        "Question updated. The previous answer was cleared.",
      askFailed:
        "The agent run failed. The question and its error detail were kept.",
      askCancelled: "The agent run was cancelled. The card was kept.",
      answerSaved: "Answer saved to the question shelf.",
      aiNotConfigured:
        "AI provider is not configured. Open Settings to add one.",
      removed: "Question removed from the shelf.",
      couldNotComplete: "The archive could not complete that request.",
    },
  },
  profile: {
    eyebrow: "User · profile",
    title: "User Profile",
    description:
      "A display name plus ordered cards that describe you. New conversations freeze the current profile into their system prompt; existing conversations keep the profile they started with.",
    save: "Save profile",
    loading: "Reading the user profile",
    errorTitle: "The user profile did not answer.",
    retry: "Retry",
    retrying: "Retrying…",
    identityEyebrow: "Identity",
    displayNameTitle: "Display name",
    nameLabel: "Name / nickname",
    nameHelp:
      "Shown in the sidebar and on your chat turns. Your sign-in username is managed separately.",
    cardsEyebrow: "Profile cards",
    cardsTitle: "How the archive should know you",
    cardsLede:
      "Each card becomes one titled line in the frozen user profile of new conversations. Cards are ordered top to bottom; existing conversations keep the profile they started with.",
    cardCountOne: "{count} card",
    cardCountOther: "{count} cards",
    empty:
      "No profile cards yet. Add one to describe your work, interests, or answer preferences.",
    addCard: "Add card",
    cardLimit: "Up to 20 cards.",
    cardTitleLabel: "Card title",
    cardTitlePlaceholder:
      "Card title, for example Work or Answer preferences",
    cardContentLabel: "Card content",
    cardContentPlaceholder:
      "Write what the archive should know. This becomes one line in the frozen user profile.",
    cardContentCount: "{count} / 2,000 characters",
    moveUpAria: "Move {title} up",
    moveDownAria: "Move {title} down",
    moveUpTitle: "Move up",
    moveDownTitle: "Move down",
    deleteAria: "Delete {title}",
    deleteTitle: "Delete card",
    cardFallback: "card",
    saveBarHelp:
      "Saving replaces every card in one transaction and updates the sidebar name.",
    saving: "Saving…",
    savedToast: "User profile saved.",
    displayNameRequired: "A display name is required.",
    cardFieldsRequired:
      "Every profile card needs both a title and content.",
  },
};
