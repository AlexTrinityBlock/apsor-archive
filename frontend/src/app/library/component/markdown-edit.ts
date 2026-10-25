/**
 * Markdown 工具列的字串操作。
 *
 * 這個模組刻意與 React、DOM、i18n 保持距離：輸入是原始字串與選取範圍，
 * 輸出是一段可套用到 textarea 的編輯結果，方便獨立推理與測試。
 */

export type MarkdownAction =
  | "bold"
  | "italic"
  | "h1"
  | "h2"
  | "h3"
  | "quote"
  | "code"
  | "list"
  | "task"
  | "link"
  | "table";

export interface MarkdownEditSelection {
  readonly start: number;
  readonly end: number;
}

export interface MarkdownEdit {
  /**
   * 這次編輯要取代的緩衝區範圍。多數動作取代選取範圍；逐行加前綴的動作
   * 則從游標所在行首開始，所以 `from` 不一定等於 `start`。
   */
  readonly from: number;
  readonly to: number;
  /** 取代 `[from, to)` 的文字。 */
  readonly text: string;
  /** 套用編輯後應留下的選取範圍。 */
  readonly selection: MarkdownEditSelection;
}

export interface MarkdownActionLabels {
  readonly boldPlaceholder: string;
  readonly italicPlaceholder: string;
  readonly codePlaceholder: string;
  readonly linkPlaceholder: string;
  readonly tableColumnPlaceholder: string;
  readonly tableCellPlaceholder: string;
}

/** 建立一個直接取代選取範圍的編輯。 */
function replace(
  start: number,
  end: number,
  text: string,
  selection: MarkdownEditSelection,
): MarkdownEdit {
  return { from: start, to: end, text, selection };
}

/** 以 `marker` 包住選取內容；沒有選取時插入 placeholder 並選取它。 */
function wrap(
  value: string,
  start: number,
  end: number,
  marker: string,
  placeholder: string,
): MarkdownEdit {
  const body = value.slice(start, end);
  if (body === "") {
    return replace(start, end, `${marker}${placeholder}${marker}`, {
      start: start + marker.length,
      end: start + marker.length + placeholder.length,
    });
  }
  return replace(start, end, `${marker}${body}${marker}`, {
    start: start + marker.length,
    end: start + marker.length + body.length,
  });
}

/** 找出 `start` 所在行的開頭；位置 0 直接視為第一行開頭。 */
function lineStartAt(value: string, start: number): number {
  if (start <= 0) {
    return 0;
  }
  return value.lastIndexOf("\n", start - 1) + 1;
}

/**
 * 在選取範圍觸及的每一行開頭加上 `prefix`。
 *
 * 這是一次涵蓋受影響行段的連續取代：從游標所在行首到選取結尾。它不會
 * 延伸到選取範圍之後，因此最後一行游標後方的文字保持不動。
 */
function prefixLines(
  value: string,
  start: number,
  end: number,
  prefix: string,
): MarkdownEdit {
  const lineStart = lineStartAt(value, start);
  const span = value.slice(lineStart, end);

  const prefixed = span
    .split("\n")
    .map((line) => `${prefix}${line}`)
    .join("\n");

  // span 一定從行首開始，因此涵蓋的行數等於換行數加一，每一行都多了前綴。
  const lineCount = span.split("\n").length;
  const added = prefix.length * lineCount;
  return {
    from: lineStart,
    to: end,
    text: prefixed,
    selection: { start: start + prefix.length, end: end + added },
  };
}

/**
 * 區塊型編輯：在游標所在行首插入多行內容，並在必要時先補一個空行，
 * 讓 Markdown 把它視為獨立區塊。
 */
function block(value: string, start: number, inner: string): MarkdownEdit {
  const lineStart = lineStartAt(value, start);
  const before = value.slice(0, lineStart);
  const leading = before === "" || before.endsWith("\n\n") ? "" : "\n";
  const text = `${leading}${inner}\n`;
  return {
    from: lineStart,
    to: lineStart,
    text,
    selection: { start: lineStart + text.length, end: lineStart + text.length },
  };
}

/**
 * 套用一個工具列動作到 `value` 的 `[start, end)` 選取範圍。
 * 所有 placeholder 都由 `labels` 傳入，模組本身不含任何語系字串。
 */
export function applyMarkdownAction(
  action: MarkdownAction,
  value: string,
  start: number,
  end: number,
  labels: MarkdownActionLabels,
): MarkdownEdit {
  switch (action) {
    case "bold":
      return wrap(value, start, end, "**", labels.boldPlaceholder);
    case "italic":
      return wrap(value, start, end, "*", labels.italicPlaceholder);
    case "h1":
      return prefixLines(value, start, end, "# ");
    case "h2":
      return prefixLines(value, start, end, "## ");
    case "h3":
      return prefixLines(value, start, end, "### ");
    case "quote":
      return prefixLines(value, start, end, "> ");
    case "list":
      return prefixLines(value, start, end, "- ");
    case "task":
      return prefixLines(value, start, end, "- [ ] ");
    case "code": {
      const body = value.slice(start, end);
      if (body.includes("\n") || body === "") {
        return block(
          value,
          start,
          `\`\`\`\n${body || labels.codePlaceholder}\n\`\`\``,
        );
      }
      return wrap(value, start, end, "`", labels.codePlaceholder);
    }
    case "link": {
      const body = value.slice(start, end);
      const linkLabel = body === "" ? labels.linkPlaceholder : body;
      const text = `[${linkLabel}](https://)`;
      // 選取 URL 區段，讓使用者可以直接輸入網址。
      return replace(start, end, text, {
        start: start + linkLabel.length + 3,
        end: start + text.length - 1,
      });
    }
    case "table":
      return block(
        value,
        start,
        [
          `| ${labels.tableColumnPlaceholder} | ${labels.tableColumnPlaceholder} |`,
          "| --- | --- |",
          `| ${labels.tableCellPlaceholder} | ${labels.tableCellPlaceholder} |`,
        ].join("\n"),
      );
  }
}
