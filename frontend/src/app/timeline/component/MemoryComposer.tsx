import { useId, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { useQueryClient } from "@tanstack/react-query";

import type { MemorySchema } from "../../generated-apis-types/schemas";

import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import { useSaveMemory } from "../../generated-apis-types/memories/memories";
import { formatNumber } from "../../../lib/format";

import { errorText, nowLocalInput } from "./helpers";

interface ParsedSupersedes {
  readonly ids: number[];
  readonly error: string | null;
}

function parseSupersedes(raw: string): ParsedSupersedes {
  const trimmed = raw.trim();
  if (trimmed.length === 0) {
    return { ids: [], error: null };
  }
  const tokens = trimmed.split(/[\s,]+/).filter(Boolean);
  const seen = new Set<number>();
  for (const token of tokens) {
    if (!/^\d+$/.test(token)) {
      return { ids: [], error: "Use comma-separated numeric memory ids, for example 12, 14." };
    }
    const id = Number(token);
    if (!Number.isSafeInteger(id) || id < 1) {
      return { ids: [], error: "Memory ids must be positive integers." };
    }
    seen.add(id);
  }
  if (seen.size > 50) {
    return { ids: [], error: "A memory can supersede at most 50 earlier memories." };
  }
  return { ids: [...seen], error: null };
}

/** Inline memory press for the timeline, with explicit deprecation semantics. */
export function MemoryComposer() {
  const toast = useToast();
  const queryClient = useQueryClient();
  const saveMemory = useSaveMemory();
  const contentId = useId();
  const occurredId = useId();
  const supersedesId = useId();

  const [content, setContent] = useState("");
  const [occurredAt, setOccurredAt] = useState(nowLocalInput);
  const [supersedes, setSupersedes] = useState("");
  const [failure, setFailure] = useState<string | null>(null);
  const [saved, setSaved] = useState<MemorySchema | null>(null);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const cleaned = content.trim();
    if (cleaned.length === 0) {
      setFailure("Write the memory before pressing it into the archive.");
      return;
    }
    if (cleaned.length > 8000) {
      setFailure("A memory is limited to 8,000 characters.");
      return;
    }
    const parsed = parseSupersedes(supersedes);
    if (parsed.error) {
      setFailure(parsed.error);
      return;
    }
    const occurred = occurredAt.length > 0 ? new Date(occurredAt) : null;
    if (occurred && Number.isNaN(occurred.getTime())) {
      setFailure("The occurred-at time is not a valid date.");
      return;
    }

    setFailure(null);
    saveMemory.mutate(
      {
        data: {
          content: cleaned,
          supersedes: parsed.ids,
          occurred_at: occurred ? occurred.toISOString() : null,
        },
      },
      {
        onSuccess: (result) => {
          setSaved(result.memory);
          setContent("");
          setSupersedes("");
          setOccurredAt(nowLocalInput());
          const deprecatedCount = result.deprecated.length;
          if (deprecatedCount === 0) {
            toast.success(`Memory ${result.memory.memory_id} saved.`);
          } else {
            const noun = deprecatedCount === 1 ? "memory is" : "memories are";
            toast.success(
              `Memory ${result.memory.memory_id} saved; ${deprecatedCount} earlier ${noun} now deprecated.`,
            );
          }
          void queryClient.invalidateQueries();
        },
        onError: (error) => {
          const message = errorText(error);
          setFailure(message);
          toast.error(`Could not save the memory. ${message}`);
        },
      },
    );
  };

  return (
    <Panel
      eyebrow="Memory · press"
      title="Press a memory"
      className="timeline-composer reveal reveal-4"
      action={
        <ButtonLink to="/memory/new" variant="ghost" size="sm">
          Full composer
          <Icon name="arrow-up-right" size={14} />
        </ButtonLink>
      }
    >
      <p className="timeline-composer__lede">
        A saved memory joins the linear timeline. Anything it supersedes is marked deprecated:
        removed from search and the default timeline, but never deleted, so the trace survives.
      </p>

      <form className="timeline-composer__form" onSubmit={handleSubmit}>
        <label className="timeline-field" htmlFor={contentId}>
          <span className="timeline-field__label">
            Content <small>required · 8,000 max</small>
          </span>
          <textarea
            id={contentId}
            value={content}
            onChange={(event) => setContent(event.target.value)}
            rows={6}
            maxLength={8000}
            required
            placeholder="What changed, what was decided, what should be remembered?"
          />
          <span className="timeline-field__count">{formatNumber(content.length)} / 8,000</span>
        </label>

        <div className="timeline-composer__grid">
          <label className="timeline-field" htmlFor={occurredId}>
            <span className="timeline-field__label">
              Occurred at <small>optional · defaults to now</small>
            </span>
            <input
              id={occurredId}
              type="datetime-local"
              value={occurredAt}
              onChange={(event) => setOccurredAt(event.target.value)}
            />
          </label>
          <label className="timeline-field" htmlFor={supersedesId}>
            <span className="timeline-field__label">
              Supersedes <small>optional · ids, comma-separated</small>
            </span>
            <input
              id={supersedesId}
              type="text"
              inputMode="numeric"
              value={supersedes}
              onChange={(event) => setSupersedes(event.target.value)}
              placeholder="12, 14"
            />
          </label>
        </div>

        {failure ? (
          <p className="timeline-composer__failure" role="alert">
            {failure}
          </p>
        ) : null}

        <Button type="submit" variant="ink" block disabled={saveMemory.isPending || content.trim().length === 0}>
          <Icon name="leaf" size={16} />
          {saveMemory.isPending ? "Pressing the memory" : "Save memory"}
        </Button>
        <p className="timeline-composer__note">
          Deprecation is a lineage action, not a delete. The superseded memories remain readable at
          their own ids and appear when history is included.
        </p>
      </form>

      {saved ? (
        <p className="timeline-composer__saved">
          Saved <Link to={`/memory/${saved.memory_id}`}>memory:{saved.memory_id}</Link> to the
          timeline.
        </p>
      ) : null}
    </Panel>
  );
}
