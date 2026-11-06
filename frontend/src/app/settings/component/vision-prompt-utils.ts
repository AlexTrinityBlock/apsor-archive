import type { Translate } from "../../i18n";

/** The two independently editable vision prompt modes. */
export const VISION_PROMPT_MODES = ["image", "document"] as const;

/** One vision prompt mode; the strings match the backend contract. */
export type VisionPromptMode = (typeof VISION_PROMPT_MODES)[number];

/** The prompt text pair returned by the vision prompt settings endpoint. */
export interface VisionPromptValues {
  readonly image_prompt: string;
  readonly document_prompt: string;
}

/** Both editable drafts, kept together so switching tabs never loses edits. */
export type VisionPromptDrafts = {
  readonly [Mode in VisionPromptMode]: string;
};

const WORD_CHARACTER = /[\p{L}\p{N}_]/u;

/** Copies persisted prompt values into the two editable drafts. */
export function toVisionPromptDrafts(
  values: VisionPromptValues,
): VisionPromptDrafts {
  return {
    image: values.image_prompt,
    document: values.document_prompt,
  };
}

/** Converts both drafts into the payload sent by the save mutation. */
export function fromVisionPromptDrafts(
  drafts: VisionPromptDrafts,
): VisionPromptValues {
  return {
    image_prompt: drafts.image.trim(),
    document_prompt: drafts.document.trim(),
  };
}

/** Compares drafts to the saved values after the same trim the API applies. */
export function visionPromptDraftsMatch(
  drafts: VisionPromptDrafts,
  values: VisionPromptValues,
): boolean {
  return (
    drafts.image.trim() === values.image_prompt.trim() &&
    drafts.document.trim() === values.document_prompt.trim()
  );
}

function isWordCharacter(character: string | undefined): boolean {
  return character !== undefined && WORD_CHARACTER.test(character);
}

/**
 * Checks a required key with word boundaries without building a regular
 * expression from data. JSON keys must appear as standalone words.
 */
export function promptIncludesKey(value: string, key: string): boolean {
  let index = value.indexOf(key);
  while (index >= 0) {
    if (
      !isWordCharacter(value[index - 1]) &&
      !isWordCharacter(value[index + key.length])
    ) {
      return true;
    }
    index = value.indexOf(key, index + 1);
  }
  return false;
}

/** Returns the required JSON keys that do not appear in the prompt text. */
export function missingVisionPromptKeys(
  value: string,
  requiredKeys: readonly string[],
): string[] {
  // The output key is a literal `language`; the `{language}` placeholder is
  // not a substitute for it. Match the backend's validation exactly.
  const searchable = value.replaceAll("{language}", " ");
  return requiredKeys.filter((key) => !promptIncludesKey(searchable, key));
}

/** Mirrors the save-time backend checks for one prompt draft. */
export function validateVisionPrompt(
  value: string,
  maxChars: number,
  requiredKeys: readonly string[],
  t: Translate,
  formatNumber: (value: number) => string,
): string | null {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return t("settings.visionPrompts.errors.required");
  }
  if (trimmed.length > maxChars) {
    return t("settings.visionPrompts.errors.maxLength", {
      max: formatNumber(maxChars),
    });
  }
  const missing = missingVisionPromptKeys(trimmed, requiredKeys);
  if (missing.length === 1) {
    return t("settings.visionPrompts.errors.missingKeysOne", {
      keys: missing[0],
    });
  }
  if (missing.length > 1) {
    return t("settings.visionPrompts.errors.missingKeys", {
      keys: missing.join(", "),
    });
  }
  return null;
}

const WARNING_TERMS = [
  {
    term: "verbatim",
    messageKey: "settings.visionPrompts.warningMissingVerbatim",
  },
  {
    term: "do not translate",
    messageKey: "settings.visionPrompts.warningMissingTranslationRule",
  },
  {
    term: "github-flavored markdown",
    messageKey: "settings.visionPrompts.warningMissingTableRule",
  },
] as const;

/** Non-blocking safety review messages for one prompt draft. */
export function visionPromptWarnings(
  value: string,
  t: Translate,
): string[] {
  const normalized = value.toLowerCase();
  return WARNING_TERMS.filter(({ term }) => !normalized.includes(term)).map(
    ({ messageKey }) => t(messageKey),
  );
}

/** A compact display form of a SHA-256 fingerprint. */
export function shortSha256(value: string): string {
  const trimmed = value.trim();
  return trimmed.length <= 12 ? trimmed : `${trimmed.slice(0, 12)}…`;
}
