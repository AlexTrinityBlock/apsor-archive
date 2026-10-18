import type { CitationSchema } from "../../generated-apis-types/schemas";
import { formatNumber } from "../../../lib/format";
import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { AnswerBody } from "./AnswerBody";
import type { AskTurn } from "./types";

interface AskThreadProps {
  readonly turns: readonly AskTurn[];
  readonly onSave: (turn: AskTurn) => void;
  readonly savingTurnId: number | null;
  readonly savedMemoryIds: Readonly<Partial<Record<number, number>>>;
  readonly onSummaryClick: (citation: CitationSchema) => void;
}

function totalTokens(turn: AskTurn): string {
  const value = turn.usage.total_tokens;
  return Number.isFinite(value) ? formatNumber(value) : "—";
}

function retrievedSummary(turn: AskTurn): string {
  const entries = Object.entries(turn.retrieved);
  if (entries.length === 0) {
    return "No sources";
  }
  return entries
    .map(([kind, count]) => `${kind} ${formatNumber(count)}`)
    .join(" · ");
}

function SaveAnswer({
  turn,
  savedMemoryId,
  savingTurnId,
  onSave,
}: {
  readonly turn: AskTurn;
  readonly savedMemoryId: number | undefined;
  readonly savingTurnId: number | null;
  readonly onSave: (turn: AskTurn) => void;
}) {
  if (savedMemoryId !== undefined) {
    return (
      <ButtonLink to={`/memory/${savedMemoryId}`} variant="ghost" size="sm">
        <Icon name="memory" size={15} />
        Open saved memory #{savedMemoryId}
      </ButtonLink>
    );
  }

  const saving = savingTurnId === turn.id;
  return (
    <Button
      variant="secondary"
      size="sm"
      onClick={() => onSave(turn)}
      disabled={savingTurnId !== null}
      aria-busy={saving}
    >
      <Icon name="leaf" size={15} />
      {saving ? "Saving…" : "Save answer as memory"}
    </Button>
  );
}

/** The conversation ledger: one question, one answer sheet, honest metadata. */
export function AskThread({
  turns,
  onSave,
  savingTurnId,
  savedMemoryIds,
  onSummaryClick,
}: AskThreadProps) {
  return (
    <ol className="ask-thread__list" aria-label="Conversation">
      {turns.map((turn, index) => {
        const savedMemoryId = savedMemoryIds[turn.id];
        return (
          <li key={turn.id}>
            <article className="ask-turn">
              <header className="ask-turn__question">
                <span className="ask-turn__index" aria-hidden="true">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <div>
                  <p className="eyebrow">Question</p>
                  <h2>{turn.question}</h2>
                </div>
              </header>

              <div className="ask-turn__sheet">
                <AnswerBody
                  answer={turn.answer}
                  citations={turn.citations}
                  onSummaryClick={onSummaryClick}
                />

                {turn.citations.length === 0 ? (
                  <p className="ask-turn__no-citations">
                    No source passages were retrieved for this answer.
                  </p>
                ) : null}

                <footer className="ask-turn__foot">
                  <dl className="ask-turn__metrics" aria-label="Answer metadata">
                    <div className="ask-turn__metric">
                      <dt>Model</dt>
                      <dd>{turn.model || "—"}</dd>
                    </div>
                    <div className="ask-turn__metric">
                      <dt>Total tokens</dt>
                      <dd>{totalTokens(turn)}</dd>
                    </div>
                    <div className="ask-turn__metric">
                      <dt>Elapsed</dt>
                      <dd>{formatNumber(turn.elapsed_ms)} ms</dd>
                    </div>
                    <div className="ask-turn__metric">
                      <dt>Retrieved</dt>
                      <dd>{retrievedSummary(turn)}</dd>
                    </div>
                  </dl>

                  <div className="ask-turn__actions">
                    <SaveAnswer
                      turn={turn}
                      savedMemoryId={savedMemoryId}
                      savingTurnId={savingTurnId}
                      onSave={onSave}
                    />
                  </div>
                </footer>
              </div>
            </article>
          </li>
        );
      })}
    </ol>
  );
}
