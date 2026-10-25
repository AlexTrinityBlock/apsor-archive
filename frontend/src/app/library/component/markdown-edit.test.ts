// @ts-expect-error -- `bun:test` 由 Bun 執行時提供；前端 tsconfig 未載入 @types/bun。
import { expect, test } from "bun:test";

import { applyMarkdownAction, type MarkdownActionLabels } from "./markdown-edit";

/** 測試用 placeholder，刻意使用中文以確認沒有硬編英文。 */
const labels: MarkdownActionLabels = {
  boldPlaceholder: "粗體文字",
  italicPlaceholder: "斜體文字",
  codePlaceholder: "程式碼",
  linkPlaceholder: "連結文字",
  tableColumnPlaceholder: "欄位",
  tableCellPlaceholder: "儲存格",
};

/** 依 toolbar 的方式把編輯結果接回原文，才能抓到取代範圍過大的問題。 */
function apply(
  action: Parameters<typeof applyMarkdownAction>[0],
  value: string,
  start: number,
  end: number,
): string {
  const edit = applyMarkdownAction(action, value, start, end, labels);
  return value.slice(0, edit.from) + edit.text + value.slice(edit.to);
}

test("bold 包住選取範圍並留下正確的選取位置", () => {
  const value = "hello world";
  const edit = applyMarkdownAction("bold", value, 0, 5, labels);

  expect(apply("bold", value, 0, 5)).toBe("**hello** world");
  expect(edit.selection).toEqual({ start: 2, end: 7 });
  expect(edit.text.slice(edit.selection.start, edit.selection.end)).toBe("hello");
});

test("bold 在空選取時插入 label 提供的 placeholder 並選取它", () => {
  const edit = applyMarkdownAction("bold", "", 0, 0, labels);

  expect(edit.text).toBe("**粗體文字**");
  expect(edit.text.slice(edit.selection.start, edit.selection.end)).toBe("粗體文字");
});

test("逐行 prefix 會套用到選取範圍觸及的每一行", () => {
  const value = "one\ntwo\nthree";
  const edit = applyMarkdownAction("h2", value, 0, value.length, labels);

  expect(edit.text).toBe("## one\n## two\n## three");
  expect(edit.selection).toEqual({ start: 3, end: value.length + 9 });
});

test("逐行 prefix 從游標所在行首開始，不覆蓋行首前的內容", () => {
  const value = "intro\ntitle here";
  const edit = applyMarkdownAction("h1", value, 6, 6, labels);

  expect(edit.from).toBe(6);
  expect(apply("h1", value, 6, 6)).toBe("intro\n# title here");
  expect(edit.selection.start).toBe(8);
});

test("list 與 task 逐行加上對應前綴", () => {
  const value = "one\ntwo";

  expect(apply("list", value, 0, value.length)).toBe("- one\n- two");
  expect(apply("task", value, 0, value.length)).toBe("- [ ] one\n- [ ] two");
});

test("code 單行使用 inline backtick，空選取使用 fenced block", () => {
  expect(apply("code", "let x = 1", 0, 9)).toBe("`let x = 1`");

  const edit = applyMarkdownAction("code", "text", 4, 4, labels);
  expect(edit.text).toContain("```\n程式碼\n```");
  expect(edit.text.endsWith("\n")).toBe(true);
});

test("link 包住選取文字並把 URL 留給使用者直接輸入", () => {
  const edit = applyMarkdownAction("link", "docs", 0, 4, labels);

  expect(edit.text).toBe("[docs](https://)");
  expect(edit.text.slice(edit.selection.start, edit.selection.end)).toBe("https://");
  expect(edit.selection).toEqual({ start: 7, end: 15 });
});

test("link 在空選取時使用 label 提供的 placeholder", () => {
  expect(apply("link", "", 0, 0)).toBe("[連結文字](https://)");
});

test("table 插入三行骨架並使用 label 提供的欄位與儲存格文字", () => {
  const edit = applyMarkdownAction("table", "", 0, 0, labels);

  expect(edit.text).toBe(
    "| 欄位 | 欄位 |\n| --- | --- |\n| 儲存格 | 儲存格 |\n",
  );
  expect(edit.selection.start).toBe(edit.text.length);
});

test("區塊插入落在游標所在行首，不會切進既有句子", () => {
  const value = "first\nsecond";
  const edit = applyMarkdownAction("table", value, 8, 8, labels);

  expect(edit.from).toBe(6);
  expect(edit.text.startsWith("\n")).toBe(true);
  expect(apply("table", value, 8, 8)).toContain("first\n\n| 欄位 | 欄位 |");
});
