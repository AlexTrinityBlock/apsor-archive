import { useEffect, useId, useRef, useState, type FormEvent, type RefObject } from "react";
import { Link } from "react-router-dom";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useI18n } from "../../i18n";

const SUGGESTED_QUERY_KEYS = [
  "insights.search.controls.suggestions.fordModelT",
  "insights.search.controls.suggestions.automaticTransmission",
  "insights.search.controls.suggestions.brakeLine",
  "insights.search.controls.suggestions.automobileHistory",
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

function latencyText(
  isFetching: boolean,
  elapsedMs: number | null,
  searching: string,
  awaiting: string,
  server: string,
): string {
  if (isFetching) {
    return searching;
  }
  if (elapsedMs === null) {
    return awaiting;
  }
  return server;
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
  const { t, formatNumber } = useI18n();
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
  const latencyLabel = latencyText(
    isFetching,
    elapsedMs,
    t("insights.search.controls.latency.searching"),
    t("insights.search.controls.latency.awaiting"),
    elapsedMs === null
      ? ""
      : t("insights.search.controls.latency.server", {
          ms: formatNumber(elapsedMs),
        }),
  );

  return (
    <section
      className="panel search-card"
      aria-label={t("insights.search.controls.aria")}
    >
      <div className="panel__body">
        <form className="search-input-wrap search-bar" role="search" onSubmit={handleSubmit}>
          <span className="search-input-wrap__icon" aria-hidden="true">
            <Icon name="search" size={20} />
          </span>
          <label className="visually-hidden" htmlFor={inputId}>
            {t("insights.search.controls.inputLabel")}
          </label>
          <input
            id={inputId}
            ref={inputRef}
            className="search-hero-input search-bar__input"
            type="search"
            value={draft}
            onChange={(event) => onDraftChange(event.target.value)}
            placeholder={t("insights.search.controls.placeholder")}
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
              aria-label={t("insights.search.controls.clear")}
              title={t("insights.search.controls.clear")}
            >
              <Icon name="close" size={16} />
            </button>
          ) : null}
          <Button type="submit" variant="ink" size="md" disabled={draft.trim().length === 0}>
            {t("insights.search.controls.submit")}
          </Button>
        </form>

        <div className="search-card__controls">
          <div className="search-knob">
            <label className="search-knob__label" htmlFor={sliderId}>
              {t("insights.search.controls.resultsPerKind")}
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
              {t("insights.search.controls.perKindValue", {
                count: formatNumber(sliderValue),
              })}
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
                {t("insights.search.controls.includeHistory")}
              </span>
              <span className="search-switch__sub" id={historySubId}>
                {t("insights.search.controls.includeHistoryHint")}
              </span>
            </span>
          </button>

          <span className={`badge search-latency ${latencyTone}`}>
            <span className="badge__dot" aria-hidden="true" />
            {latencyLabel}
          </span>
        </div>

        <div className="search-suggestions">
          <span className="mono-label">{t("insights.search.controls.suggested")}</span>
          {SUGGESTED_QUERY_KEYS.map((suggestionKey) => (
            <button
              key={suggestionKey}
              type="button"
              className="suggestion-chip"
              onClick={() => {
                onSubmit(t(suggestionKey));
                inputRef.current?.focus();
              }}
            >
              {t(suggestionKey)}
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
                <Loader
                  size={13}
                  label={t("insights.search.controls.savingQuestion")}
                />
                {t("insights.search.controls.saving")}
              </>
            ) : (
              <>
                <Icon name="plus" size={14} />
                {t("insights.search.controls.saveQuestion")}
              </>
            )}
          </Button>
          <Link className="text-link search-suggestions__link" to="/questions">
            {t("insights.search.controls.savedQuestions")}
          </Link>
        </div>
      </div>
    </section>
  );
}
