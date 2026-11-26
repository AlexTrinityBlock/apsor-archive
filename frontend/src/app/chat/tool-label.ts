import type { Translate } from "../i18n";
import type { ResourceMeta } from "./types";

/**
 * The heading for a tool step in the transcript.
 *
 * Most tools keep their technical name. `present_resource` is the exception:
 * its raw name says nothing about the file or memory the reader just received,
 * so the heading names the presented resource instead.
 */
export function toolStepLabel(
  tool: string | null,
  resourceType: ResourceMeta["resourceType"] | null,
  t: Translate,
): string {
  if (tool === "present_resource") {
    if (resourceType === "memory") {
      return t("chat.resource.presentedMemory");
    }
    if (resourceType === "file") {
      return t("chat.resource.presentedFile");
    }
  }
  return tool ?? t("chat.tool.resultFallback");
}
