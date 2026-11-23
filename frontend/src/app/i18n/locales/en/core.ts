/**
 * Core interface strings: shell, authentication, dashboard, shared controls,
 * and stable backend error codes. English is the source of truth.
 */
export const core = {
  app: {
    name: "Apsor Archive",
    studio: "Archive Studio",
  },
  boot: {
    missingRoot: "The archive root element is missing from index.html.",
  },
  common: {
    retry: "Retry",
    retrying: "Retrying…",
    close: "Close",
    notAvailable: "—",
  },
  nav: {
    ariaPrimary: "Primary",
    ariaArchive: "Archive navigation",
    skipToArchive: "Skip to the archive",
    openNavigation: "Open navigation",
    closeNavigation: "Close navigation",
    expandRail: "Expand navigation rail",
    collapseRail: "Collapse navigation rail",
    chat: "Chat",
    library: "File library",
    timeline: "Timeline",
    memory: "Memory",
    search: "Search",
    dashboard: "Dashboard",
    settings: "Settings",
    about: "About",
    openProfile: "Open User Profile",
    userProfile: "User profile",
    profile: "User profile",
    personalSection: "Personal",
    accounts: "Accounts",
    changePassword: "Change password",
    signOut: "Sign out",
    sessionSection: "Session",
    systemStatus: "System status",
    localArchive: "Local archive",
    checkingServices: "Checking local services",
    apiOffline: "API offline",
    localFirst: "Local-first",
    version: "v{version}",
    owner: "Owner",
  },
  status: {
    ok: "ok",
    degraded: "degraded",
    error: "error",
    missing: "missing",
    configured: "configured",
    disabled: "disabled",
    unknown: "unknown",
    detail: "DB {database} · cache {cache} · AI {ai}",
  },
  loader: {
    defaultLabel: "Loading the archive",
  },
  route: {
    fallbackLabel: "Opening the archive",
    fallbackEyebrow: "Opening the archive",
    errorEyebrow: "Archive · route error",
    errorTitle: "The archive could not open this view.",
    errorDescription:
      "The page stopped before it could render. Your files and memories are unchanged.",
    chunkTitle: "A newer build is ready.",
    chunkDescription:
      "Reload to collect the current build. This usually happens right after a deployment while an older tab is still open.",
    reload: "Reload archive",
    backToOverview: "Back to overview",
    unknownError: "The archive could not open this view.",
  },
  notFound: {
    eyebrow: "Archive · 404",
    title: "This page is not in the archive.",
    description:
      "The address may be mistyped, or the page has moved to another room. Nothing was deleted; the archive is still here.",
    returnOverview: "Return to the overview",
    searchArchive: "Search the archive",
  },
  auth: {
    loadingEyebrow: "Apsor Archive · private archive",
    loadingLabel: "Checking the archive session",
    opening: "Opening the archive…",
    loadErrorEyebrow: "The archive did not answer",
    loadErrorTitle: "We could not check the session.",
    tryAgain: "Try again",
    frame: {
      asideAria: "Apsor Archive",
      asideEyebrow: "Private field station · Vol. 01",
      asideHeadline: "Memory is not data.",
      asideHeadlineAccent: "It is growth.",
      asideDescription:
        "A local-first archive of files, memories, and the passages between them. Private accounts; no cloud workspace; the rings stay on this machine.",
      localFirst: "Local-first",
      privateAccounts: "Private accounts",
      noTelemetry: "No telemetry",
      footerProtocol: "0.7px hairline protocol",
      footerYear: "MMXXVI",
    },
    login: {
      eyebrow: "Account sign-in",
      title: "Return to the archive.",
      description:
        "The archive is private. Sign in with your own account to read your files and memories; every account keeps its own archive.",
      footer:
        "There is no cloud recovery or self-service registration. The root account manages accounts on this machine.",
      username: "Username",
      credentialLabel: "Password",
      showPassword: "Show password",
      hidePassword: "Hide password",
      show: "Show",
      hide: "Hide",
      submit: "Enter the archive",
      submitting: "Opening the archive…",
    },
    setup: {
      eyebrow: "First run · create root",
      title: "Press the first ring.",
      description:
        "This archive has no accounts yet. Create the root account; it manages accounts and global settings, and keeps its own private archive.",
      footer:
        "The password is hashed with Argon2. There is no email recovery or cloud reset. Root can create accounts for other people later.",
      username: "Username",
      usernameHint:
        "3–64 characters; letters, digits, dot, dash, underscore; start and end with a letter or digit.",
      credentialLabel: "Password",
      credentialHint: "At least 10 characters. There is no recovery.",
      confirmCredential: "Confirm password",
      credentialTooShort: "Use at least 10 characters for the password.",
      credentialMismatch: "The password confirmation does not match.",
      submit: "Create the root account",
      submitting: "Pressing the first ring…",
    },
    changePassword: {
      eyebrow: "Account security",
      title: "Change your password",
      description:
        "Update the password for this account. Your other sessions are signed out; this one stays open.",
      forcedTitle: "Set a new password before continuing.",
      forcedDescription:
        "This account is using a temporary password. Choose your own password to open the archive.",
      forcedFooter:
        "You can sign out instead, but the archive stays locked until the password changes.",
      currentPassword: "Current password",
      newPassword: "New password",
      confirmPassword: "Confirm new password",
      passwordHint:
        "At least 10 characters. Other sessions are signed out after the change.",
      currentRequired: "Enter your current password.",
      currentInvalid: "The current password is not correct.",
      mismatch: "The new passwords do not match.",
      weak: "Use at least 10 characters for the new password.",
      submit: "Change password",
      submitting: "Changing password…",
      success: "Password changed. Other sessions were signed out.",
    },
  },
  accounts: {
    eyebrow: "Root management",
    title: "Accounts",
    description:
      "Manage who can open this archive. Every account keeps a private archive; root also manages global settings.",
    countOne: "{count} account",
    countOther: "{count} accounts",
    create: "Create account",
    createTitle: "Create an account",
    createDescription:
      "The new account receives its own private archive and a one-time temporary password.",
    username: "Username",
    usernameHint:
      "3–64 characters; letters, digits, dot, dash, underscore; start and end with a letter or digit.",
    usernameRequired: "Enter a username with at least 3 characters.",
    displayName: "Display name",
    displayNameHint: "How this person appears in the archive, up to 80 characters.",
    displayNameRequired: "Enter a display name.",
    createSubmit: "Create account",
    creating: "Creating account…",
    cancel: "Cancel",
    working: "Working…",
    empty: "No accounts to show.",
    emptyDescription: "The root account should always be listed here.",
    loading: "Reading accounts…",
    roleRoot: "Root",
    roleUser: "User",
    active: "Active",
    disabled: "Disabled",
    mustChange: "Must change password",
    currentAccount: "Current account",
    created: "Created",
    lastLogin: "Last sign-in",
    never: "Never",
    usageTitle: "Token usage",
    totalTokens: "Total tokens",
    promptTokens: "Prompt",
    completionTokens: "Completion",
    cachedTokens: "Cached",
    apiCalls: "API calls",
    turns: "Turns",
    lastActivity: "Last activity",
    noActivity: "No activity yet",
    tokenSplitAria:
      "Prompt {prompt} tokens; completion {completion} tokens",
    impersonate: "Impersonate",
    impersonateTitle: "Impersonate user",
    impersonateDescription:
      "Open a session as this account. You will see its private archive and act with its permissions; root-only pages are hidden until you return to root.",
    impersonateWarning:
      "This is a trusted root capability. Every action is recorded as this account, and the root account remains responsible for it.",
    impersonateError: "The account could not be impersonated.",
    disable: "Disable",
    enable: "Enable",
    resetPassword: "Reset password",
    disableConfirm:
      "Disabling this account revokes every active session immediately. The person cannot sign in again until you enable it.",
    enableConfirm:
      "Enabling this account lets the person sign in again with their existing password. They must start a new session.",
    resetTitle: "Reset password",
    resetDescription:
      "A new temporary password replaces the current one and revokes every active session. The person must change it at the next sign-in.",
    temporaryPasswordTitle: "Temporary password",
    temporaryPasswordDescription:
      "Share this password with the account holder through a private channel. It cannot be shown again.",
    temporaryPasswordWarning:
      "This password is shown once and is not stored in the browser. If you lose it, reset the password again.",
    temporaryPasswordLabel: "One-time password",
    copy: "Copy password",
    copied: "Copied",
    done: "Done",
    createSuccess: "Account created.",
    disableSuccess: "Account disabled. Every session was revoked.",
    enableSuccess: "Account enabled.",
    resetSuccess: "Password reset. Every session was revoked.",
    error: "The account could not be updated.",
    quotasTitle: "Usage allowances",
    quotasManage: "Manage usage",
    quotaChat: "Chat tokens",
    quotaEmbedding: "Embedding characters",
    quotaWebSearch: "Web searches",
    quotaWebFetch: "Web fetches",
    quotaAllowed: "Allowed",
    quotaBlocked: "Blocked",
    quotaUnlimited: "Unlimited",
    quotaUsageAria: "{category}: {used} used of {granted}",
    quotaBeforeReset: "before reset {value}",
    quotaDialogTitle: "Usage allowances",
    quotaDialogDescription:
      "Set the allowance for {name}. A blank grant means unlimited; zero blocks all usage of that category.",
    quotaAccountingHint:
      "Chat tokens include chat runs, summaries, extraction, memory titles, and vision. Embedding usage is measured in input characters.",
    quotaUsed: "Used this cycle",
    quotaLifetime: "Lifetime",
    quotaBeforeResetLabel: "Before reset",
    quotaRemaining: "Remaining",
    quotaEnabledLabel: "Category enabled",
    quotaEnabledHint:
      "When blocked, the category cannot be used even if a grant remains.",
    quotaGrantLabel: "Grant",
    quotaGrantHint:
      "Leave blank for unlimited. 0 is a valid grant that blocks all usage.",
    quotaGrantInvalid:
      "Enter a whole number of 0 or greater, or leave the grant blank for unlimited.",
    quotaSave: "Save allowance",
    quotaSaving: "Saving…",
    quotaTopUpTitle: "Top up",
    quotaTopUpHint: "Add to the current finite grant. Existing usage is unchanged.",
    quotaTopUpUnlimited:
      "Unlimited allowances do not need a top-up. Set a finite grant first.",
    quotaTopUpAmount: "Top-up amount",
    quotaTopUp: "Top up",
    quotaTopUpInvalid: "Enter a whole number greater than 0.",
    quotaResetTitle: "Reset usage",
    quotaResetDescription:
      "Start a new cycle. The lifetime counter is kept as the new before-reset baseline.",
    quotaReset: "Reset usage",
    quotaResetConfirm:
      "Reset the current usage of {used}? The lifetime total is preserved and the reset cannot be undone.",
    quotaResetConfirmAction: "Confirm reset",
    quotaResetCancel: "Keep usage",
    quotaResetting: "Resetting…",
    quotaClose: "Close",
    quotaSaveSuccess: "Usage allowance saved.",
    quotaTopUpSuccess: "Usage allowance topped up.",
    quotaResetSuccess: "Usage reset. The lifetime total was preserved.",
    quotaError: "The usage allowance could not be updated.",
    modelTitle: "Model assignment",
    modelManage: "Manage model",
    modelLoading: "Reading model assignment…",
    modelUnavailable: "The model assignment could not be read.",
    modelPrimary: "Primary",
    modelAuxiliary: "Auxiliary",
    modelUnassigned: "Unassigned",
    modelBudgetShort: "{tokens} ctx",
    modelCompactionShort: "{tokens} compact",
    modelWarningCount: "{count} warnings",
    modelWarningCountOne: "{count} warning",
    modelDegradedBadge: "Degraded",
    modelDialogTitle: "Model assignment",
    modelDialogDescription:
      "Choose the two provider endpoints {name} uses. Every changed connection is tested before it is saved.",
    modelDialogHelp:
      "Model names and effort values are free text. The catalog is advisory; the connection test is the only validation.",
    modelEndpoint: "Endpoint",
    modelEndpointPlaceholder: "Select an endpoint",
    modelEndpointUnavailable: "{label} (unavailable)",
    modelEndpointError: "The endpoint list did not answer.",
    modelEndpointEmpty:
      "No active, keyed chat endpoint is available. Add one in Settings → Provider registry.",
    modelName: "Model",
    modelNameHint:
      "Free text, up to 128 characters. Known names are suggestions, not a closed list.",
    modelOptionPrice: "${input} in · ${output} out per MTok",
    modelUnknown:
      "Not in the price catalog: no tier, no automatic escalation, and the cost is shown as unpriced.",
    modelFamilyMismatch:
      "This model is usually served by {family}; the call will probably fail.",
    modelEffort: "Reasoning effort",
    modelEffortHint:
      "Anything is accepted here. Test is the only validation.",
    modelPrimaryEffortEmpty:
      "Leave blank to use the provider default.",
    modelEffortHintsAnthropic:
      "Anthropic accepts low · medium · high · xhigh · max.",
    modelEffortHintsDeepSeek:
      "DeepSeek accepts low · high · max; none disables thinking.",
    modelEffortHintsOpenAI:
      "OpenAI/GPT accepts none · minimal · low · medium · high · xhigh · max.",
    modelEffortHintsOther:
      "Check the provider documentation for the accepted values.",
    modelTest: "Test",
    modelTesting: "Testing…",
    modelTestOk: "Connected · {latency} ms · {model}",
    modelTestOkNoModel: "Connected · {latency} ms",
    modelTestFailed: "Test failed",
    modelTestError: "The connection test did not answer.",
    modelTestHint:
      "Test the endpoint, model, and effort before saving a change.",
    modelTestRequired: "Test this slot to enable saving.",
    modelSlotPrimaryTitle: "Primary slot",
    modelSlotPrimaryDescription: "Agent chat uses the primary endpoint.",
    modelSlotAuxiliaryTitle: "Auxiliary slot",
    modelSlotAuxiliaryDescription:
      "Summaries, memory, ingestion, and vision use the auxiliary endpoint.",
    modelSlotRequired: "Choose an endpoint and a model for both slots.",
    modelAuxEffortRequired: "The auxiliary effort is required.",
    modelAuxInherited:
      "This account currently inherits the primary endpoint for auxiliary work. Saving writes an explicit auxiliary assignment, which needs its own test.",
    modelBudgetTitle: "Context budget",
    modelBudgetDescription:
      "The maximum input sent to the provider for one call, and when older turns are folded away.",
    modelBudgetPercent: "{percent}% of the context window",
    modelContextWindow: "Context window",
    modelContextWindowHint:
      "8,000–2,000,000 tokens. Leave blank to use the deployment default.",
    modelCompactionThreshold: "Compaction threshold",
    modelThresholdHint:
      "1,000–1,000,000 tokens; it must be below the context window. Leave blank to use the deployment default.",
    modelThresholdOrder:
      "The compaction threshold must be less than the context window.",
    modelBudgetInvalid:
      "Enter a whole number within the allowed range, or leave the field blank.",
    modelCostHint:
      "Prompts above 100,000 tokens cost 5x more per token, including cache reads. 90,000 leaves ~10K of headroom.",
    modelWarningsTitle: "Advisory warnings",
    modelWarningUnknownModel:
      "The model is not in the price catalog: no tier, no automatic escalation, and the cost is unpriced.",
    modelWarningFamilyMismatch:
      "The model is normally served by a different provider family; the call may fail.",
    modelWarningWindowAboveCatalog:
      "The context window is above the model's catalog window. The stored value is kept.",
    modelWarningLongPromptStep:
      "Above the model's long-prompt threshold every token costs more, including cache reads.",
    modelWarningAuxInherited:
      "The auxiliary slot currently inherits the primary endpoint.",
    modelDegradedNoProvider:
      "The primary endpoint was deleted or is invalid. Chat is unavailable until a new endpoint is assigned.",
    modelDegradedProviderInactive:
      "The assigned endpoint is inactive or has no usable key. Requests fail until it is fixed.",
    modelDegradedAuxNoProvider:
      "The auxiliary endpoint was deleted or is invalid. Background AI is unavailable.",
    modelDegradedInvalidThreshold:
      "The stored budget pair is not usable with the deployment defaults; the deployment budget applies.",
    modelDegradedUnknown: "The effective configuration is degraded ({reason}).",
    modelResetTitle: "Reset assignment",
    modelResetDescription:
      "Clear both endpoints and both budgets. The account then has no model assignment.",
    modelResetConfirm:
      "Reset the model assignment for {name}? Chat and background AI stop until a new assignment is saved.",
    modelResetConfirmAction: "Confirm reset",
    modelResetCancel: "Keep assignment",
    modelReset: "Reset assignment",
    modelResetting: "Resetting…",
    modelSave: "Save assignment",
    modelSaving: "Saving…",
    modelSaveBlocked: "Test every changed slot before saving.",
    modelSaveNeedsPrimaryTest:
      "The primary endpoint changed. Run Test on it before saving.",
    modelSaveNeedsAuxTest:
      "The auxiliary endpoint changed. Run Test on it before saving.",
    modelSaveNeedsBothTests:
      "Both endpoints changed. Run Test on each before saving.",
    modelSaveNeedsPrimaryFields:
      "Choose a primary endpoint and enter a model.",
    modelSaveNeedsAuxFields:
      "Choose an auxiliary endpoint, model, and reasoning effort.",
    modelSaveNeedsBudgetRange:
      "The context window or compaction threshold is outside the allowed range.",
    modelSaveNeedsBudgetOrder:
      "The compaction threshold must be lower than the context window.",
    modelSaveNeedsEndpoints: "Loading chat endpoints…",
    modelSaveWaitingForTest: "Waiting for the connection test to finish…",
    modelClose: "Close",
    modelSaveSuccess: "Model assignment saved.",
    modelResetSuccess: "Model assignment reset.",
    modelError: "The model assignment could not be updated.",
  },
  notices: {
    title: "System notices",
    openCount: "{count} open",
    count: "{count}×",
    lastSeen: "Last seen {time}",
    resolve: "Resolve",
    resolveAll: "Resolve all",
    resolving: "Resolving…",
    empty: "No provider failures are waiting. The chains are quiet.",
    loading: "Reading system notices…",
    loadError: "System notices did not answer.",
    resolveSuccess: "Provider notice resolved.",
    resolveAllSuccess: "All provider notices resolved.",
    resolveError: "Could not resolve the provider notice.",
  },
  impersonation: {
    eyebrow: "Root session",
    switchUser: "Switch user",
    switchUserAria: "Switch user. Currently signed in as {name}.",
    switchUserTitle: "Open the user switcher",
    viewingAs: "Viewing as",
    dialogTitle: "Impersonate user",
    dialogDescription:
      "Choose a normal account. Root will see that account's private archive and act with its permissions; root-only pages are hidden until you return to root.",
    searchLabel: "Search accounts",
    searchPlaceholder: "Search by name or username",
    loading: "Reading accounts…",
    loadError: "The account list could not be read.",
    noAccounts: "No other accounts yet.",
    noAccountsDescription: "Create a normal account before impersonating someone.",
    noMatches: "No matching accounts.",
    noMatchesDescription: "Try a different display name or username.",
    disabledReason: "This account is disabled, so it cannot be impersonated.",
    mustChangeReason:
      "This account must change its password before it can be impersonated.",
    impersonate: "Impersonate",
    impersonateUser: "Impersonate {name}",
    impersonating: "Impersonating…",
    error: "The account could not be impersonated.",
    bannerAria: "Impersonation active",
    bannerTitle: "Viewing as {name}",
    bannerDescription:
      "The root account ({root}) is acting with this account's permissions and private archive. Root-only pages are hidden until you return.",
    root: "root",
    returnToRoot: "Return to root",
    returnedToRoot: "Returned to the root account.",
    stopError: "Could not return to the root account.",
    stop: {
      eyebrow: "Root re-authentication",
      title: "Return to root",
      description:
        "Confirm the root password to end this impersonation session. This prevents the impersonated person from taking over the root account.",
      actorLabel: "Root account",
      passwordLabel: "Root password",
      passwordHint:
        "The password is checked against the root account before a fresh root session is issued.",
      passwordRequired: "Enter the root password.",
      showPassword: "Show root password",
      hidePassword: "Hide root password",
      show: "Show",
      hide: "Hide",
      submit: "Return to root",
      submitting: "Returning to root…",
    },
  },
  copy: {
    copy: "Copy",
    copied: "Copied",
    copiedToast: "Copied to the clipboard.",
    failed: "The browser could not copy that text.",
  },
  queryState: {
    defaultLoadingLabel: "Reading the archive",
    readInterrupted: "Read interrupted",
    didNotAnswer: "The archive did not answer.",
    genericError: "The archive could not be read.",
  },
  searchField: {
    label: "Search files, memories, and summaries",
    placeholder: "Search files, memories, paths...",
    submit: "Search",
  },
  toast: {
    dismiss: "Dismiss notification",
  },
  home: {
    eyebrow: "Archive dashboard",
    title: "Archive Dashboard",
    search: "Search",
    statsAria: "Archive statistics",
    statFiles: "Files archived",
    statFilesNote: "{size} stored locally",
    statChunks: "Indexed chunks",
    statChunksNote: "Current indexed knowledge units",
    statMemories: "Memories",
    statMemoriesNote: "{active} active · {deprecated} deprecated",
    statSummaries: "AI summaries",
    statSummariesNote: "Recorded document summaries",
    countsUnavailable: "Counts unavailable",
    statusChecking: "Checking archive",
    statusReadingHealth: "Reading local service health",
    statusOffline: "Archive offline",
    statusHealthNoAnswer: "The health endpoint did not answer.",
    statusDegradedDatabase: "Degraded · database {status}",
    statusDegraded: "Degraded · {status}",
    statusDegradedCache: "Degraded · cache {status}",
    statusLive: "Live Archive · v{version}",
    recentFilesAria: "Reading recent files",
    recentFilesTitle: "Recent Files",
    recentFilesErrorTitle: "Recent files could not be read.",
    recentFilesErrorFallback: "Neither the timeline nor the root shelf answered.",
    recentFilesEmptyTitle: "No files on the shelf yet.",
    recentFilesEmptyDescription:
      "Upload a text file, PDF, or image to begin the archive.",
    uploadFile: "Upload a file",
    viewAllFiles: "View all files",
    fallbackNote:
      "The timeline did not answer, so this shelf lists the newest files at the archive root.",
    retryTimeline: "Retry timeline",
    pathUnavailable: "Path unavailable",
    fileChunks: "{count} chunks",
    timelineAria: "Reading recent timeline events",
    timelineTitle: "Recent Timeline Events",
    timelineWindow: "30-day window",
    timelineCount: "{shown} of {total} events",
    timelineLastDays: "Last {days} days",
    timelineErrorTitle: "The timeline did not answer.",
    timelineErrorFallback: "The 30-day window could not be read.",
    timelineEmptyTitle: "No events in this window.",
    timelineEmptyDescription:
      "Files, memories, and summaries appear here as the archive grows.",
    openTimeline: "Open timeline",
    viewTimeline: "View timeline",
    eventMemorySuperseded: "Memory superseded",
    eventMemoryCrystallized: "Memory recorded",
    eventSummarySynthesized: "Summary synthesized",
    eventFileCreated: "File created",
    eventFileUpdated: "File updated",
    eventMemoryFallback: "Memory #{id}",
    eventSummaryFallback: "Summary #{id}",
    eventFileFallback: "File #{id}",
    noExcerpt: "No excerpt recorded.",
    readMemory: "Read memory",
    openInLibrary: "Open in File Library",
    statsErrorTitle: "Live counts are unavailable.",
    statsErrorFallback: "The stats endpoint did not answer.",
  },
  languagePanel: {
    eyebrow: "Interface",
    title: "Language",
    description:
      "Choose the language of the interface. The change applies immediately; there is no Save button.",
    note:
      "This changes only the interface. Files, memories, summaries, prompts, and citations keep their original language.",
    aria: "Interface language",
  },
  settingsNav: {
    aria: "Settings sections",
    title: "Settings",
    sectionCount: "{count} sections",
    expand: "Expand settings navigation",
    collapse: "Collapse settings navigation",
    systemPrompt: "System prompt",
    frequentPrompts: "Frequent prompts",
    model: "Model",
    providers: "Provider registry",
    diagnostics: "Diagnostics",
    agentRuntime: "Agent runtime",
    ingestRuntime: "Ingestion runtime",
    maintenance: "Maintenance",
    language: "Language",
  },
  settings: {
    model: {
      title: "Model assignment",
      lede:
        "The two endpoints your account uses. Primary endpoints serve agent chat; auxiliary endpoints serve summaries, memory, ingestion, and vision. Your administrator assigns both.",
      loadReadingAria: "Reading model assignment",
      loadErrorTitle: "The model assignment did not answer.",
      primary: "Primary",
      auxiliary: "Auxiliary",
      inherited: "Inherited",
      endpoint: "Endpoint",
      provider: "Provider",
      model: "Model",
      effort: "Effort",
      effortEmpty: "Provider default",
      price: "Price",
      pricing: "${input} in · ${output} out per MTok",
      pricingUnpriced: "unpriced",
      tierUnpriced: "unpriced",
      noEndpoint: "No endpoint",
      budgetTitle: "Context budget",
      budgetContext: "Context window",
      budgetThreshold: "Compaction threshold",
      budgetDefaultHint:
        "A blank budget inherits the deployment default from the agent runtime settings.",
      deploymentDefault: "Deployment default",
      warningsTitle: "Advisory warnings",
      warningUnknownModel:
        "The model is not in the price catalog: no tier, no automatic escalation, and the cost is shown as unpriced.",
      warningFamilyMismatch:
        "The model is normally served by a different provider family; calls may fail.",
      warningWindowAboveCatalog:
        "The context window is above the model's catalog window. The stored value is kept.",
      warningLongPromptStep:
        "Above the model's long-prompt threshold every token costs more, including cache reads.",
      warningAuxInherited:
        "The auxiliary slot currently inherits the primary endpoint.",
      degradedNoProvider:
        "The primary endpoint was deleted or is invalid. Chat is unavailable until a new endpoint is assigned.",
      degradedProviderInactive:
        "The assigned endpoint is inactive or has no usable key. Requests fail until it is fixed.",
      degradedAuxNoProvider:
        "The auxiliary endpoint was deleted or is invalid. Background AI is unavailable.",
      degradedInvalidThreshold:
        "The stored budget pair is not usable with the deployment defaults; the deployment budget applies.",
      degradedUnknown: "The effective configuration is degraded ({reason}).",
      unassigned: "No model assigned — ask the administrator.",
      unassignedHint:
        "Chat and background AI are unavailable until an administrator assigns both endpoints.",
      unassignedBadge: "Unassigned",
      adminNote: "Assigned by your administrator.",
      updated: "Updated",
    },
  },
  errors: {
    invalid_request: "The request was not valid. Check the values and try again.",
    unauthorized: "Your session has expired. Sign in to continue.",
    invalid_credentials: "The username or password was not accepted.",
    login_failed: "The username or password was not accepted.",
    account_disabled:
      "This account is disabled. Ask the root account to enable it.",
    password_change_required:
      "This account must change its password before continuing.",
    current_password_invalid: "The current password is not correct.",
    account_not_found: "That account could not be found.",
    username_taken: "That username is already taken.",
    cannot_disable_root: "The root account cannot be disabled.",
    last_root_protected: "The only root account must stay enabled.",
    cannot_impersonate_self: "The root account cannot impersonate itself.",
    cannot_impersonate_root: "A root account cannot be impersonated.",
    account_not_impersonatable:
      "This account cannot be impersonated. It may be disabled or must change its password first.",
    not_impersonating: "This session is not impersonating an account.",
    impersonation_password_change_forbidden:
      "A password cannot be changed while impersonating an account. Return to root first.",
    impersonation_password_invalid: "The root password is not correct.",
    setup_required: "The archive still needs its first root account.",
    setup_already_complete:
      "The archive already has accounts. Sign in instead.",
    invalid_username:
      "Use 3–64 letters, digits, dots, dashes, or underscores; start and end with a letter or digit.",
    invalid_profile:
      "The display name must contain between 1 and 80 characters.",
    weak_password: "Use at least 10 characters for the password.",
    password_mismatch: "The password confirmation does not match.",
    login_throttled:
      "Too many sign-in attempts. Wait a moment and try again.",
    rate_limited: "Too many requests. Wait a moment and try again.",
    agent_not_configured:
      "The agent is not configured yet. Add an AI provider in Settings.",
    agent_conversation_busy:
      "The agent is busy with another turn. Wait for it to finish and try again.",
    agent_conversation_archived:
      "This conversation is archived. Restore it before making changes.",
    agent_run_not_retryable: "This run can no longer be retried.",
    agent_invalid_system_prompt:
      "The system prompt is not valid. Check the text and try again.",
    agent_system_prompt_not_found: "That system prompt could not be found.",
    usage_limit_exceeded:
      "This account has reached its chat token allowance. Ask the administrator to top it up or reset it.",
    web_usage_limit_exceeded:
      "This account has reached its web search or fetch allowance. Ask the administrator to top it up or reset it.",
    invalid_usage_quota: "That usage allowance change is not valid.",
    model_not_assigned:
      "No model is assigned to this account. Ask the administrator.",
    provider_inactive:
      "The assigned model endpoint is inactive or has no usable key. Ask the administrator.",
    ai_not_configured:
      "Vision extraction is not configured. Add a vision-capable provider in Settings.",
    invalid_vision_prompt:
      "The vision prompt is not valid. Check the required JSON keys and character limit.",
    ingest_job_conflict:
      "This file already has an active ingestion job. Wait for it to finish.",
    ingest_source_stale:
      "The file changed while it was being re-ingested. The newer version remains current.",
    file_version_conflict:
      "This file changed since it was loaded. Reload the preview and try again.",
    unsupported_file_type: "This file type cannot be re-ingested.",
    file_not_found:
      "That file could not be found. It may be deleted, historical, or unavailable.",
    file_content_unavailable:
      "The file content is not available. It may still be processing or may have been removed.",
    storage_unavailable:
      "File storage is unavailable. Try again shortly.",
    not_found: "The requested item could not be found.",
    internal_error: "The archive hit an internal error. Try again.",
    network_error:
      "The archive could not be reached. Check the connection and try again.",
    forbidden: "You do not have permission to do that.",
    conflict:
      "That action conflicts with the current state. Refresh and try again.",
    generic: "The archive could not complete that action.",
  },
};
