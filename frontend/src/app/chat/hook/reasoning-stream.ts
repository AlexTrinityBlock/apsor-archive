import type { ChatStreamSegment } from "./useChatStream";

/** Append one streamed reasoning piece to the newest assistant segment. */
export function appendReasoningDelta(
  segments: readonly ChatStreamSegment[],
  delta: string,
): ChatStreamSegment[] {
  const base =
    segments.length > 0
      ? [...segments]
      : [{ index: 1, text: "", toolCalls: [], reasoning: "", reasoningTokens: 0 }];
  const lastIndex = base.length - 1;
  base[lastIndex] = {
    ...base[lastIndex],
    reasoning: base[lastIndex].reasoning + delta,
  };
  return base;
}
