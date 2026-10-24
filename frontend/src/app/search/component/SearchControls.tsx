import { useEffect, useId, useRef, useState, type FormEvent, type RefObject } from "react";
import { Link } from "react-router-dom";

import { formatNumber } from "../../../lib/format";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";

const SUGGESTED_QUERIES = [
  "Ford Model T",
  "automatic transmission",
  "brake line",
  "history of the automobile",
] as const;

const SLIDER_COMMIT_MS = 250;

interface SearchControlsProps {
  readonly draft: string;
  readonly onDraftChange: (value: string) => void;
  readonly onSubmit: (value: string) => void;
  readonly onClear: () => void;
  readonly inputRef: RefObject<HTMLInputElement | null>;
  readonly resultNumber: number;
  readonly onResultNumberChange: (value: number) => void;
  readonly includeHistory: boolean;
  readonly onIncludeHistoryChange: (value: boolean) => void;
  readonly elapsedMs: number | null;
  readonly isFetching: boolean;
  readonly canClear: boolean;
  readonly canSaveQuestion: boolean;
  readonly isSavingQuestion: boolean;
  readonly onSaveQuestion: () => void;
}

function latencyText(isFetching: boolean, elapsedMs: number | null): string {
  if (isFetching) {
    return "Searching…";
  }
  if (elapsedMs === null) {
    return "Awaiting query";
  }
  return `Server: ${formatNumber(elapsedMs)} ms`;
}

/**
 * The full query surface: the large input, the two request knobs, real server
 * latency, suggestion chips, and the saved-question shortcut.
 */
export function SearchControls({
  draft,
  onDraftChange,
  onSubmit,
  onClear,
  inputRef,
  resultNumber,
  onResultNumberChange,
  includeHistory,
  onIncludeHistoryChange,
  elapsedMs,
  isFetching,
  canClear,
  canSaveQuestion,
  isSavingQuestion,
  onSaveQuestion,
}: SearchControlsProps) {
  const inputId = useId();
  const sliderId = useId();
  const historyTitleId = useId();
  const historySubId = useId();
  const [sliderValue, setSliderValue] = useState(resultNumber);
  const [lastResultNumber, setLastResultNumber] = useState(resultNumber);
  const sliderCommitTimer = useRef<number | null>(null);

  if (lastResultNumber !== resultNumber) {
    setLastResultNumber(resultNumber);
    setSliderValue(resultNumber);
  }

  useEffect(() => {
    return () => {
      if (sliderCommitTimer.current !== null) {
        window.clearTimeout(sliderCommitTimer.current);
      }
    };
  }, []);

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    onSubmit(draft);
  };

  const handleClear = () => {
    onClear();
    inputRef.current?.focus();
  };

  const handleSliderChange = (value: number) => {
    setSliderValue(value);
    if (sliderCommitTimer.current !== null) {
      window.clearTimeout(sliderCommitTimer.current);
    }
    sliderCommitTimer.current = window.setTimeout(() => {
      sliderCommitTimer.current = null;
      if (value !== resultNumber) {
        onResultNumberChange(value);
      }
    }, SLIDER_COMMIT_MS);
  };

  const commitSliderNow = () => {
    if (sliderCommitTimer.current !== null) {
      window.clearTimeout(sliderCommitTimer.current);
      sliderCommitTimer.current = null;
    }
    if (sliderValue !== resultNumber) {
      onResultNumberChange(sliderValue);
    }
  };

  const latencyTone = elapsedMs !== null && !isFetching ? "badge--moss" : "badge--neutral";

  return (
    <section className="panel search-card" aria-label="Search controls">
      <div className="panel__body">
        <form className="search-input-wrap search-bar" role="search" onSubmit={handleSubmit}>
          <span className="search-input-wrap__icon" aria-hidden="true">
            <Icon name="search" size={20} />
          </span>
          <label className="visually-hidden" htmlFor={inputId}>
            Search files, memories, and summaries
          </label>
          <input
            id={inputId}
            ref={inputRef}
            className="search-hero-input search-bar__input"
            type="search"
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            placeholder="Search a phrase, a path, or a half-remembered detail…"
            autoComplete="off"
            spellCheck={false}
            enterKeyHint="search"
            autoFocus
          />
          {canClear ? (
            <button
              type="button"
              className="search-bar__clear"
              onClick={handleClear}
              aria-label="Clear query"
              title="Clear query"
            >
              <Icon name="close" size={16} />
            </button>
          ) : null}
          <Button type="submit" variant="ink" size="md" disabled={draft.trim().length === 0}>
            Search
          </Button>
        </form>

        <div className="search-card__controls">
          <div className="search-knob">
            <label className="search-knob__label" htmlFor={sliderId}>
              Results per kind
            </label>
            <input
              id={sliderId}
              className="search-slider"
              type="range"
              min={1}
              max={10}
              step={1}
              value={sliderValue}
              onChange={(event) => handleSliderChange(Number(event.target.value))}
              onPointerUp={commitSliderNow}
              onBlur={commitSliderNow}
            />
            <output className="search-knob__value" htmlFor={sliderId}>
              N = {sliderValue}
            </output>
          </div>

          <button
            type="button"
            role="switch"
            aria-checked={includeHistory}
            aria-labelledby={historyTitleId}
            aria-describedby={historySubId}
            className="search-switch"
            onClick={() => onIncludeHistoryChange(!includeHistory)}
          >
            <span className="search-switch__track" aria-hidden="true">
              <span className="search-switch__knob" />
            </span>
            <span className="search-switch__copy">
              <span className="search-switch__title" id={historyTitleId}>
                Include history
              </span>
              <span className="search-switch__sub" id={historySubId}>
                Superseded files and deprecated memories
              </span>
            </span>
          </button>

          <span className={`badge search-latency ${latencyTone}`}>
            <span className="badge__dot" aria-hidden="true" />
            {latencyText(isFetching, elapsedMs)}
          </span>
        </div>

        <div className="search-suggestions">
          <span className="mono-label">Suggested queries</span>
          {SUGGESTED_QUERIES.map((suggestion) => (
            <button
              key={suggestion}
              type="button"
              className="suggestion-chip"
              onClick={() => {
                onSubmit(suggestion);
                inputRef.current?.focus();
              }}
            >
              {suggestion}
            </button>
          ))}
          <span className="search-suggestions__spacer" aria-hidden="true" />
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onSaveQuestion}
            disabled={!canSaveQuestion || isSavingQuestion}
            aria-busy={isSavingQuestion}
          >
            {isSavingQuestion ? (
              <>
                <Loader size={13} label="Saving question" />
                Saving…
              </>
            ) : (
              <>
                <Icon name="plus" size={14} />
                Save question
              </>
            )}
          </Button>
          <Link className="text-link search-suggestions__link" to="/questions">
            Saved questions
          </Link>
        </div>
      </div>
    </section>
  );
}
