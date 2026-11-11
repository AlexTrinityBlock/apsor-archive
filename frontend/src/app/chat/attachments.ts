/**
 * Composer-side helpers for temporary chat images.
 *
 * Uploads are account-scoped and survive navigation; the composer only holds
 * the ids and display metadata needed for an optimistic preview.
 */
import { ApiError } from "../../apis/fetch-client";
import { getUploadAgentChatAttachmentUrl } from "../generated-apis-types/agent/agent";
import type { AgentChatAttachmentSchema } from "../generated-apis-types/schemas";
import { getActiveLocale, translate } from "../i18n";
import type { ChatAttachmentView } from "./types";

export const SUPPORTED_CHAT_IMAGE_TYPES = [
  "image/png",
  "image/jpeg",
  "image/webp",
] as const;

export const MAX_CHAT_IMAGES_PER_MESSAGE = 4;

/** A URL-safe token that carries one composer upload across an abort. */
export function createChatUploadToken(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  return Array.from(bytes, (byte) => byte.toString(16).padStart(2, "0")).join(
    "",
  );
}

export type ComposerAttachmentStatus = "uploading" | "ready" | "error";

export interface ComposerAttachment {
  readonly key: string;
  readonly status: ComposerAttachmentStatus;
  readonly fileName: string;
  readonly clientToken: string;
  readonly progress: number;
  readonly attachment: ChatAttachmentView | null;
  readonly error: string | null;
}

export interface ChatAttachmentUploadOptions {
  readonly file: File;
  readonly clientToken: string;
  readonly signal?: AbortSignal;
  readonly onProgress?: (percent: number) => void;
}

interface ErrorRecord {
  [key: string]: unknown;
}

function isRecord(value: unknown): value is ErrorRecord {
  return typeof value === "object" && value !== null;
}

function clampPercent(value: number): number {
  return Math.max(0, Math.min(100, Math.round(value)));
}

function xhrPayload(xhr: XMLHttpRequest): unknown {
  const text = xhr.responseText;
  if (!text) {
    return null;
  }
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return text;
  }
}

function payloadText(payload: unknown, key: string): string | null {
  if (!isRecord(payload)) {
    return null;
  }
  const value = payload[key];
  return typeof value === "string" && value.trim().length > 0 ? value : null;
}

function xhrFailure(xhr: XMLHttpRequest): ApiError {
  const payload = xhrPayload(xhr);
  const code = payloadText(payload, "error") ?? "http_error";
  const status = xhr.status;
  // Match the shared fetch mutator so an expired session still leaves the
  // signed-in shell even when the request was an XHR upload.
  if (
    typeof window !== "undefined" &&
    (code === "account_disabled" ||
      (status === 401 &&
        (code === "authentication_required" || code === "unauthorized")))
  ) {
    window.dispatchEvent(new Event("apsor-archive:unauthorized"));
  }
  return new ApiError(
    status,
    code,
    payloadText(payload, "detail") ??
      translate(getActiveLocale(), "core.errors.generic"),
    payload,
  );
}

/**
 * Upload one chat image through XHR so the composer can show real byte
 * progress and abort the request before the server finishes storing it.
 *
 * This is the deliberate upload exception to the generated `apiFetch` client:
 * fetch has no portable upload-progress event. The URL, response shape, and
 * `ApiError` contract still come from the generated API surface.
 *
 * @param options - Upload inputs.
 * @param options.file - The image selected or pasted by the user.
 * @param options.clientToken - Browser-generated token used for cancellation.
 * @param options.signal - Optional signal whose abort calls `xhr.abort()`.
 * @param options.onProgress - Optional integer-percent progress callback.
 * @returns The stored attachment after the server returns `201`.
 * @throws {ApiError} When the server rejects the upload.
 * @throws {DOMException} With name `AbortError` when the signal aborts it.
 */
export function uploadChatAttachment({
  file,
  clientToken,
  signal,
  onProgress,
}: ChatAttachmentUploadOptions): Promise<AgentChatAttachmentSchema> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) {
      reject(new DOMException("The upload was aborted.", "AbortError"));
      return;
    }
    const xhr = new XMLHttpRequest();
    let lastPercent = -1;
    let settled = false;

    const abort = () => {
      if (settled) {
        return;
      }
      xhr.abort();
    };
    const finish = () => {
      signal?.removeEventListener("abort", abort);
    };
    const fail = (error: unknown) => {
      if (settled) {
        return;
      }
      settled = true;
      finish();
      reject(error);
    };

    xhr.open("POST", getUploadAgentChatAttachmentUrl());
    xhr.upload.onprogress = (event) => {
      if (!event.lengthComputable || event.total <= 0) {
        return;
      }
      const percent = clampPercent((event.loaded / event.total) * 100);
      if (percent === lastPercent) {
        return;
      }
      lastPercent = percent;
      onProgress?.(percent);
    };
    xhr.onload = () => {
      if (settled) {
        return;
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        const payload = xhrPayload(xhr);
        if (isRecord(payload) && typeof payload.id === "number") {
          settled = true;
          finish();
          resolve(payload as unknown as AgentChatAttachmentSchema);
          return;
        }
        fail(
          new ApiError(
            0,
            "invalid_response",
            translate(getActiveLocale(), "core.errors.generic"),
            payload,
          ),
        );
        return;
      }
      fail(xhrFailure(xhr));
    };
    xhr.onerror = () => {
      fail(
        new ApiError(
          0,
          "network_error",
          translate(getActiveLocale(), "core.errors.network_error"),
          null,
        ),
      );
    };
    xhr.onabort = () => {
      fail(new DOMException("The upload was aborted.", "AbortError"));
    };
    xhr.ontimeout = () => {
      fail(
        new ApiError(
          0,
          "network_error",
          translate(getActiveLocale(), "core.errors.network_error"),
          null,
        ),
      );
    };
    signal?.addEventListener("abort", abort, { once: true });

    const form = new FormData();
    form.append("file", file);
    form.append("client_token", clientToken);
    xhr.send(form);
  });
}

/** True when an upload rejection came from the composer aborting it. */
export function isUploadAbortError(error: unknown): boolean {
  return error instanceof DOMException && error.name === "AbortError";
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
