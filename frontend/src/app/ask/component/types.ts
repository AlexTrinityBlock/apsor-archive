import type { CitationSchema } from "../../generated-apis-types/schemas";

/** One question and the grounded answer the archive returned for it. */
export interface AskTurn {
  readonly id: number;
  readonly question: string;
  readonly answer: string;
  readonly citations: CitationSchema[];
  readonly model: string;
  readonly usage: Record<string, number>;
  readonly elapsed_ms: number;
  readonly retrieved: Record<string, number>;
}
