import { Icon } from "../../../component/Icon";
import { formatArgumentValue } from "../../../chat/format";
import { textField } from "../../trace";
import type { PanelProps } from "./common";

const SUGGESTIONS: Readonly<Record<string, string>> = {
  invalid_tool_arguments:
    "Re-issue the call with the required scalar arguments; arrays and objects must match the tool catalog.",
  memory_confirmation_required:
    "The keeper must explicitly confirm the memory text before it can be pressed into the archive.",
  tool_unavailable:
    "This tool is not part of the conversation's frozen tool set. Start a new thread to refresh it.",
  tool_execution_failed:
    "The underlying archive service failed. Retry once the local API and its providers are healthy.",
  file_not_found: "Check the file id and whether the leaf was removed or superseded.",
  memory_not_found: "Check the memory id; deprecated leaves remain readable, removed ones do not.",
  invalid_chunk_window:
    "Choose a chunk inside the file's recorded range, then retry the read.",
};

function suggestionFor(code: string | null): string {
  if (!code) {
    return "No structured error code was recorded. Read the detail and arguments to decide the next step.";
  }
  return (
    SUGGESTIONS[code] ??
    "The tool rejected this call. Adjust the arguments or ask for a narrower operation."
  );
}

/** A repair bench for any failed or unstructured tool result. */
export function ToolErrorPanel({ item }: PanelProps) {
  const code = item.errorCode ?? textField(item.data, "code");
  const detail =
    item.detail ??
    textField(item.data, "detail") ??
    textField(item.data, "message") ??
    "The tool did not return a structured error detail.";
  const argumentEntries = item.arguments ? Object.entries(item.arguments) : [];

  return (
    <div className="pi-repair">
      <div className="pi-repair__lamp" aria-hidden="true">
        <span />
      </div>
      <header className="pi-repair__head">
        <span className="pi-repair__mark" aria-hidden="true">
          <Icon name="info" size={18} />
        </span>
        <div>
          <p className="eyebrow">Repair bench · tool error</p>
          <strong>{code ?? "unstructured_error"}</strong>
        </div>
      </header>

      <p className="pi-repair__detail">{detail}</p>

      <section className="pi-repair__section">
        <p className="eyebrow">Suggested next step</p>
        <p>{suggestionFor(code)}</p>
      </section>

      {argumentEntries.length > 0 ? (
        <section className="pi-repair__section">
          <p className="eyebrow">Arguments received</p>
          <dl className="pi-repair__args">
            {argumentEntries.map(([key, value]) => (
              <div key={key}>
                <dt>{key}</dt>
                <dd>{formatArgumentValue(value)}</dd>
              </div>
            ))}
          </dl>
        </section>
      ) : null}

      <p className="pi-repair__note">
        The model sees a bounded XML error value; this panel is a UI-only
        diagnostic view.
      </p>
    </div>
  );
}
