/**
 * Composer-side helpers for temporary chat images.
 *
 * Uploads are account-scoped and survive navigation; the composer only holds
 * the ids and display metadata needed for an optimistic preview.
 */
import type { AgentChatAttachmentSchema } from "../generated-apis-types/schemas";
import type { ChatAttachmentView } from "./types";

export const SUPPORTED_CHAT_IMAGE_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
] as const;

export const MAX_CHAT_IMAGES_PER_MESSAGE = 4;

export type ComposerAttachmentStatus = "uploading" | "ready" | "error";

export interface ComposerAttachment {
  readonly key: string;
  readonly status: ComposerAttachmentStatus;
  readonly fileName: string;
  readonly attachment: ChatAttachmentView | null;
  readonly error: string | null;
}

export function attachmentView(
  attachment: AgentChatAttachmentSchema,
): ChatAttachmentView {
  return {
    id: attachment.id,
    fileName: attachment.file_name,
    mimeType: attachment.mime_type,
    sizeBytes: attachment.size_bytes,
    width: attachment.width,
    height: attachment.height,
    contentUrl: attachment.content_url,
  };
}

export function isChatImageFile(file: File): boolean {
  const mime = file.type.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  if ((SUPPORTED_CHAT_IMAGE_TYPES as readonly string[]).includes(mime)) {
    return true;
  }
  const name = file.name.trim().toLowerCase();
  return [".png", ".jpg", ".jpeg", ".webp"].some((suffix) =>
    name.endsWith(suffix),
  );
}

/** Collect every image file in a clipboard payload, including unnamed ones. */
export function clipboardImageFiles(data: DataTransfer | null): File[] {
  if (!data) {
    return [];
  }
  const candidates = Array.from(data.files ?? []);
  if (candidates.length === 0) {
    for (const item of Array.from(data.items ?? [])) {
      if (item.kind !== "file") {
        continue;
      }
      const file = item.getAsFile();
      if (file) {
        candidates.push(file);
      }
    }
  }
  return candidates.filter(isChatImageFile);
}

export function nameClipboardImage(file: File, index: number): File {
  if (file.name.trim().length > 0) {
    return file;
  }
  const mime = file.type.split(";", 1)[0]?.trim().toLowerCase() ?? "";
  let suffix = ".png";
  if (mime === "image/jpeg") {
    suffix = ".jpg";
  } else if (mime === "image/webp") {
    suffix = ".webp";
  }
  return new File([file], `pasted-image-${Date.now()}-${index + 1}${suffix}`, {
    type: file.type || "image/png",
    lastModified: file.lastModified,
  });
}

export function formatAttachmentBytes(value: number): string {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${Math.round(value / 1024)} KB`;
  }
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}
