import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import type { SummarySchema } from "../../generated-apis-types/schemas";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import { useCreateSummary } from "../../generated-apis-types/memories/memories";
import { formatDate, formatDateTime, formatNumber } from "../../../lib/format";

import { errorText } from "./helpers";

interface SummaryPanelProps {
  readonly rangeStart: string | null;
  readonly rangeEnd: string | null;
  readonly caption: string;
  readonly disabled: boolean;
}

/** Distils the displayed range into one indexed summary. */
export function SummaryPanel({ rangeStart, rangeEnd, caption, disabled }: SummaryPanelProps) {
  const toast = useToast();
  const queryClient = useQueryClient();
  const createSummary = useCreateSummary();
  const [result, setResult] = useState<SummarySchema | null>(null);
  const [failure, setFailure] = useState<string | null>(null);

  const handleSummarize = () => {
    if (!rangeStart || !rangeEnd) {
      return;
    }
    setFailure(null);
    createSummary.mutate(
      {
        data: {
          period_start: rangeStart,
          period_end: rangeEnd,
          force: true,
        },
      },
      {
        onSuccess: (summary) => {
          setResult(summary);
          toast.success(
            summary.generator === "deepseek"
              ? `Summary ${summary.memory_summary_id} created by ${summary.model ?? "DeepSeek"}.`
              : `Summary ${summary.memory_summary_id} created with the extractive fallback.`,
          );
          void queryClient.invalidateQueries();
        },
        onError: (error) => {
          const message = errorText(error);
          setFailure(message);
          toast.error(`Could not summarize this range. ${message}`);
        },
      },
    );
  };

  return (
    <Panel
      eyebrow="Memory distillate"
      title="Summarize this range"
      className="timeline-summary reveal reveal-4"
      action={<Badge tone="ochre">force = true</Badge>}
    >
      <p className="timeline-summary__lede">
        The displayed window becomes <code>period_start</code> and <code>period_end</code>. The
        endpoint prefers DeepSeek and falls back to an extractive summary when the model is
        unavailable.
      </p>
      <p className="timeline-summary__range">{caption}</p>

      <Button
        variant="primary"
        block
        onClick={handleSummarize}
        disabled={disabled || createSummary.isPending || !rangeStart || !rangeEnd}
      >
        <Icon name="spark" size={16} />
        {createSummary.isPending ? "Distilling the range" : "Summarize this range"}
      </Button>
      <p className="timeline-summary__hint">
        Summaries collect active, unsummarized memories only. A failed model call still returns a
        usable extractive result.
      </p>

      {failure ? (
        <p className="timeline-summary__failure" role="alert">
          {failure}
        </p>
      ) : null}

      {result ? (
        <div className="timeline-summary__result">
          <header className="timeline-summary__result-head">
            <div>
              <p className="eyebrow">New summary</p>
              <strong>summary:{result.memory_summary_id}</strong>
            </div>
            <Badge tone={result.generator === "deepseek" ? "moss" : "ochre"} dot>
              {result.generator}
            </Badge>
          </header>
          <p className="timeline-summary__result-content">{result.content}</p>
          {result.themes.length > 0 ? (
            <ul className="timeline-summary__themes" aria-label="Summary themes">
              {result.themes.map((theme, index) => (
                <li key={`${theme}-${index}`}>{theme}</li>
              ))}
            </ul>
          ) : null}
          <dl className="timeline-summary__result-meta">
            <div>
              <dt>Model</dt>
              <dd>
                <code>{result.model ?? "not reported"}</code>
              </dd>
            </div>
            <div>
              <dt>Memories</dt>
              <dd>{formatNumber(result.memory_count)}</dd>
            </div>
            <div>
              <dt>Created</dt>
              <dd>{formatDateTime(result.created_at)}</dd>
            </div>
          </dl>
          <p className="timeline-summary__result-period">
            Covers {formatDate(result.period_start)} {"\u2013"} {formatDate(result.period_end)}
          </p>
        </div>
      ) : null}
    </Panel>
  );
}
