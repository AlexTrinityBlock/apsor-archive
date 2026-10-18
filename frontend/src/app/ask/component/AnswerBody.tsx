import type { CitationSchema } from "../../generated-apis-types/schemas";
import { CitationChip } from "./CitationChip";

const CITATION_KINDS = new Set(["file", "memory", "summary"]);

interface AnswerBodyProps {
  readonly answer: string;
  readonly citations: readonly CitationSchema[];
  readonly onSummaryClick: (citation: CitationSchema) => void;
}

function isDigits(value: string): boolean {
  if (value.length === 0) {
    return false;
  }
  for (const character of value) {
    if (character < "0" || character > "9") {
      return false;
    }
  }
  return true;
}

/** Returns the label without brackets when a token is a valid citation. */
function citationLabel(token: string): string | null {
  if (!token.startsWith("[") || !token.endsWith("]")) {
    return null;
  }
  const body = token.slice(1, -1);
  const colonIndex = body.indexOf(":");
  if (colonIndex <= 0) {
    return null;
  }
  const kind = body.slice(0, colonIndex);
  if (!CITATION_KINDS.has(kind)) {
    return null;
  }
  const rest = body.slice(colonIndex + 1);
  const hashIndex = rest.indexOf("#");
  const idPart = hashIndex >= 0 ? rest.slice(0, hashIndex) : rest;
  const chunkPart = hashIndex >= 0 ? rest.slice(hashIndex + 1) : null;
  if (!isDigits(idPart)) {
    return null;
  }
  if (chunkPart !== null && !isDigits(chunkPart)) {
    return null;
  }
  return body;
}

/**
 * Splits plain text into text runs and citation tokens without a regular
 * expression, preserving every whitespace character for `pre-wrap`.
 */
function tokenizeAnswer(answer: string): string[] {
  const pieces: string[] = [];
  let cursor = 0;

  while (cursor < answer.length) {
    const open = answer.indexOf("[", cursor);
    if (open < 0) {
      pieces.push(answer.slice(cursor));
      break;
    }
    const close = answer.indexOf("]", open + 1);
    if (close < 0) {
      pieces.push(answer.slice(cursor));
      break;
    }
    const candidate = answer.slice(open, close + 1);
    if (citationLabel(candidate) === null) {
      pieces.push(answer.slice(cursor, open + 1));
      cursor = open + 1;
      continue;
    }
    if (open > cursor) {
      pieces.push(answer.slice(cursor, open));
    }
    pieces.push(candidate);
    cursor = close + 1;
  }

  return pieces;
}

function resolveCitation(
  label: string,
  citations: readonly CitationSchema[],
): CitationSchema | undefined {
  const exact = citations.find((citation) => citation.label === label);
  if (exact) {
    return exact;
  }
  // A model may append a chunk suffix to a summary label even though the
  // backend labels summary sources by id alone. Resolve it when possible.
  const hashIndex = label.indexOf("#");
  if (label.startsWith("summary:") && hashIndex > 0) {
    const baseLabel = label.slice(0, hashIndex);
    return citations.find(
      (citation) => citation.kind === "summary" && citation.label === baseLabel,
    );
  }
  return undefined;
}

/**
 * Renders the answer as plain text. Citation tokens become chips; everything
 * else stays a text node, so file content can never execute as HTML.
 */
export function AnswerBody({ answer, citations, onSummaryClick }: AnswerBodyProps) {
  const pieces = tokenizeAnswer(answer);

  return (
    <div className="ask-answer">
      {pieces.map((piece, index) => {
        const label = citationLabel(piece);
        const citation = label ? resolveCitation(label, citations) : undefined;
        if (citation) {
          return (
            <CitationChip
              key={`${citation.label}-${index}`}
              citation={citation}
              onSummaryClick={onSummaryClick}
            />
          );
        }
        if (piece.length === 0) {
          return null;
        }
        return <span key={`text-${index}`}>{piece}</span>;
      })}
    </div>
  );
}
