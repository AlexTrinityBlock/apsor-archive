import { CopyButton } from "../../../component/CopyButton";
import { useI18n } from "../../../i18n";
import { numberField, textField } from "../../trace";
import { LivePanel, PanelEmpty, type PanelProps } from "./common";

/** 以毫秒或秒呈現經過時間。 / Render an elapsed duration in milliseconds or seconds. */
function elapsedLabel(
  value: number,
  formatNumber: (value: number) => string,
): string {
  if (value >= 1_000) {
    return `${(value / 1_000).toFixed(2)} s`;
  }
  return `${formatNumber(value)} ms`;
}

/**
 * `calculate`：算式收據，只顯示後端已算好的結果。
 * `calculate`: an arithmetic receipt that only shows the backend's result.
 *
 * 面板不解析或執行 expression；它只是把已記錄的字串與數值排成收據。
 * The panel never parses or evaluates the expression; it only sets the
 * recorded string and number as a receipt.
 */
export function CalculatePanel({ item }: PanelProps) {
  const { t, formatNumber } = useI18n();
  if (item.live || item.status.toLowerCase() === "running") {
    return (
      <LivePanel item={item} detail={t("chat.panels.calculate.liveDetail")} />
    );
  }

  const data = item.data;
  const expression =
    textField(data, "expression") ?? textField(item.arguments, "expression");
  if (!expression) {
    return (
      <PanelEmpty
        icon="spark"
        title={t("chat.panels.calculate.unavailableTitle")}
        detail={t("chat.panels.calculate.unavailableDetail")}
      />
    );
  }

  const stored = numberField(data, "result");
  const formatted =
    textField(data, "formatted") ?? (stored === null ? null : String(stored));
  const elapsed =
    item.durationMs === null
      ? null
      : elapsedLabel(item.durationMs, formatNumber);
  const showStored =
    stored !== null && formatted !== null && String(stored) !== formatted;

  return (
    <div className="pi-calc">
      <header className="pi-calc__head">
        <p className="eyebrow">{t("chat.panels.calculate.eyebrow")}</p>
      </header>

      <div className="pi-calc__equation">
        <span className="visually-hidden">
          {t("chat.panels.calculate.expression")}
        </span>
        <code className="pi-calc__expression">{expression}</code>
        {formatted !== null ? (
          <>
            <span className="pi-calc__equal" aria-hidden="true">
              {" = "}
            </span>
            <span className="visually-hidden">
              {t("chat.panels.calculate.result")}
            </span>
            <output className="pi-calc__result">{formatted}</output>
          </>
        ) : null}
      </div>

      {formatted === null ? (
        <p className="pi-calc__empty">{t("chat.panels.calculate.noResult")}</p>
      ) : null}

      <div className="pi-calc__actions">
        <CopyButton
          value={expression}
          label={t("chat.panels.calculate.copyExpression")}
        />
        {formatted !== null ? (
          <CopyButton
            value={formatted}
            label={t("chat.panels.calculate.copyResult")}
          />
        ) : null}
      </div>

      {elapsed !== null || showStored ? (
        <dl className="pi-calc__meta">
          {elapsed !== null ? (
            <div>
              <dt>{t("chat.panels.calculate.elapsed")}</dt>
              <dd>{elapsed}</dd>
            </div>
          ) : null}
          {showStored ? (
            <div>
              <dt>{t("chat.panels.calculate.storedValue")}</dt>
              <dd>
                <code>{String(stored)}</code>
              </dd>
            </div>
          ) : null}
        </dl>
      ) : null}

      <details className="pi-calc__raw">
        <summary>{t("chat.panels.calculate.rawExpression")}</summary>
        <code>{expression}</code>
      </details>
    </div>
  );
}
