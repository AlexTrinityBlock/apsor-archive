import { useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { ApiError } from "../../apis/fetch-client";
import { Badge } from "../component/Badge";
import { PageHeader } from "../component/PageHeader";
import { useToast } from "../component/Toast";
import { useAskKnowledge } from "../generated-apis-types/ai/ai";
import { useSaveMemory } from "../generated-apis-types/memories/memories";
import type { CitationSchema } from "../generated-apis-types/schemas";
import { AskComposer } from "./component/AskComposer";
import {
  AskErrorState,
  AskPending,
  SuggestedQuestions,
} from "./component/AskStates";
import { AskThread } from "./component/AskThread";
import { summarySourceId } from "./component/citationLinks";
import { SourcesRail } from "./component/SourcesRail";
import type { AskTurn } from "./component/types";
import "./ask.css";

const INITIAL_RESULT_NUMBER = 4;

/**
 * The RAG reading room. Conversation is intentionally local to this mount: the
 * archive stores memories, not chat transcripts. Every answer keeps its
 * citations, model, usage, and retrieval counts beside it.
 */
export function AskPage() {
  const askKnowledge = useAskKnowledge();
  const saveMemory = useSaveMemory();
  const queryClient = useQueryClient();
  const toast = useToast();

  const [turns, setTurns] = useState<AskTurn[]>([]);
  const [question, setQuestion] = useState("");
  const [resultNumber, setResultNumber] = useState(INITIAL_RESULT_NUMBER);
  const [lastError, setLastError] = useState<unknown>(null);
  const [savingTurnId, setSavingTurnId] = useState<number | null>(null);
  const [savedMemoryIds, setSavedMemoryIds] = useState<
    Partial<Record<number, number>>
  >({});

  const nextTurnId = useRef(1);
  const askInFlight = useRef(false);
  const latestTurn = turns.at(-1) ?? null;

  const handleAsk = async (rawQuestion: string) => {
    const trimmed = rawQuestion.trim();
    if (trimmed.length < 2 || askInFlight.current) {
      return;
    }

    askInFlight.current = true;
    setLastError(null);
    try {
      const response = await askKnowledge.mutateAsync({
        data: {
          question: trimmed,
          result_number: resultNumber,
        },
      });
      const turnId = nextTurnId.current;
      nextTurnId.current += 1;
      setTurns((current) => [
        ...current,
        {
          id: turnId,
          question: trimmed,
          answer: response.answer,
          citations: response.citations,
          model: response.model,
          usage: response.usage,
          elapsed_ms: response.elapsed_ms,
          retrieved: response.retrieved,
        },
      ]);
      setQuestion((current) => (current.trim() === trimmed ? "" : current));
      void queryClient.invalidateQueries();
    } catch (error) {
      setLastError(error);
    } finally {
      askInFlight.current = false;
    }
  };

  const handleAskSuggestion = (suggestedQuestion: string) => {
    setQuestion(suggestedQuestion);
    void handleAsk(suggestedQuestion);
  };

  const handleSave = async (turn: AskTurn) => {
    if (savingTurnId !== null) {
      return;
    }
    setSavingTurnId(turn.id);
    try {
      const saved = await saveMemory.mutateAsync({
        data: {
          content: `Question: ${turn.question}\n\nAnswer: ${turn.answer}`,
        },
      });
      await queryClient.invalidateQueries();
      setSavedMemoryIds((current) => ({
        ...current,
        [turn.id]: saved.memory.memory_id,
      }));
      toast.success(`Answer saved as memory #${saved.memory.memory_id}.`);
    } catch (error) {
      if (error instanceof ApiError) {
        if (error.status === 422) {
          toast.error(`This answer could not be saved: ${error.detail}`);
        } else if (error.status === 503) {
          toast.error("The memory store is unavailable. The answer remains here.");
        } else {
          toast.error(error.detail);
        }
      } else {
        toast.error("The answer could not be saved.");
      }
    } finally {
      setSavingTurnId(null);
    }
  };

  const handleSummaryClick = (citation: CitationSchema) => {
    const targetId = summarySourceId(citation);
    if (targetId === null) {
      return;
    }
    document
      .getElementById(targetId)
      ?.scrollIntoView({ behavior: "smooth", block: "center" });
  };

  return (
    <div className="page ask-page">
      <PageHeader
        eyebrow="Ask · grounded answers"
        title="Ask the archive."
        description="A question becomes a handful of current passages, then an answer that must cite them. If the archive cannot ground a claim, the room stays quiet rather than guessing."
        meta={<span>Hybrid search → DeepSeek → citations</span>}
        actions={<Badge tone="vermilion">No answer without a source</Badge>}
      />

      <div className="ask-room reveal reveal-2">
        <div className="ask-thread">
          {turns.length === 0 ? (
            <SuggestedQuestions
              onSelect={handleAskSuggestion}
              disabled={askKnowledge.isPending}
            />
          ) : (
            <AskThread
              turns={turns}
              onSave={(turn) => {
                void handleSave(turn);
              }}
              savingTurnId={savingTurnId}
              savedMemoryIds={savedMemoryIds}
              onSummaryClick={handleSummaryClick}
            />
          )}

          {askKnowledge.isPending ? <AskPending /> : null}
          {lastError ? <AskErrorState error={lastError} /> : null}
        </div>

        <SourcesRail turn={latestTurn} onSummaryClick={handleSummaryClick} />

        <AskComposer
          question={question}
          onQuestionChange={setQuestion}
          resultNumber={resultNumber}
          onResultNumberChange={setResultNumber}
          onSubmit={(value) => {
            void handleAsk(value);
          }}
          pending={askKnowledge.isPending}
        />
      </div>
    </div>
  );
}
