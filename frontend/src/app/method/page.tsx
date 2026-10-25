import { Link } from "react-router-dom";

import { Icon } from "../component/Icon";
import { FileVsMemoryDiagram } from "./component/FileVsMemoryDiagram";
import { HybridSearchDiagram } from "./component/HybridSearchDiagram";
import "./method.css";

const PRINCIPLES = [
  {
    index: "01",
    eyebrow: "Two libraries",
    title: "Paths for files, moments for memory.",
    body: (
      <>
        <strong>File library:</strong> every file keeps a stable path coordinate and
        immutable bytes. Re-uploading the same path creates a new edition, not an
        overwrite. <strong>Memory library:</strong> every entry carries its own moment and
        can supersede an earlier belief without erasing it. One index searches both.
      </>
    ),
  },
  {
    index: "02",
    eyebrow: "Hybrid retrieval",
    title: "Lexical precision plus semantic reach.",
    body: (
      <>
        BM25 reads CJK bigrams, word n-grams, and character trigrams. A vector lane reads
        cosine similarity. Each lane returns its own candidates; reciprocal rank fusion
        merges them, and the response reports{" "}
        <code>text_candidates</code>, <code>vector_candidates</code>,{" "}
        <code>merged</code>, and <code>deduplicated</code> so the search can be audited.
      </>
    ),
  },
  {
    index: "03",
    eyebrow: "Timeline sampling",
    title: "Sparse anchors, explicit gaps.",
    body: (
      <>
        A long range returns five anchors per event type instead of every row. Gaps are
        reported as <code>skips</code>, and a day-by-day <code>density</code> strip keeps
        the shape of the interval visible. An empty range returns an empty list, not an
        invented event.
      </>
    ),
  },
  {
    index: "04",
    eyebrow: "Citation contract",
    title: "An answer without a receipt is a rumour.",
    body: (
      <>
        Answers are written only from retrieved passages and must cite{" "}
        <code>[file:12#15]</code> or <code>[memory:1015]</code>. Without a configured
        provider the endpoint returns <code>503 ai_not_configured</code> rather than
        generating prose.
      </>
    ),
  },
] as const;

const CITATION_LOOP = [
  {
    index: "01",
    title: "Retrieve",
    body: "One hybrid query selects passages from files, memories, and summaries. Each passage keeps its source kind, source id, and chunk index.",
  },
  {
    index: "02",
    title: "Answer",
    body: "The model answers from those excerpts only and emits citation tags. Those tags are the answer's receipts, not decoration.",
  },
  {
    index: "03",
    title: "Verify",
    body: "A file citation opens the File Library at the cited chunk. A memory citation opens the Memory vault at that entry.",
  },
  {
    index: "04",
    title: "Keep",
    body: "The answer, its citation chips, and the conversation stay beside the saved question, so the verification can be repeated.",
  },
] as const;

/**
 * The method essay: two provenance shapes, one retrieval index, and the
 * citation contract that keeps answers inspectable.
 */
export function MethodPage() {
  return (
    <div className="page method-page">
      <div className="content-container content-container--reading">
        <header className="method-hero">
          <div className="method-hero__top">
            <span className="shell-tag">Method · field notes // Rev. 2026.10</span>
            <span className="mono-label">Two libraries. One index.</span>
          </div>
          <h1 className="method-hero__title">
            Two libraries.
            <span>
              One <em>tree.</em>
            </span>
          </h1>
          <p className="method-hero__lede">
            Most knowledge tools flatten an archive into a bag of vectors. Apsor Archive
            keeps two shapes at once: the branching path of a file and the linear grain
            of a memory. Both are indexed, cited, and read in the same archive.
          </p>
          <p className="method-hero__note">
            <Icon name="info" size={15} />
            <span>
              The tree is a conceptual figure for how paths and memories are filed. It
              is not a workspace, a data source, or a route in this interface.
            </span>
          </p>
          <dl className="meta-grid method-meta">
            <div className="meta-item">
              <dt className="meta-key">Archive</dt>
              <dd className="meta-value">Files, memories, summaries</dd>
            </div>
            <div className="meta-item">
              <dt className="meta-key">Retrieval</dt>
              <dd className="meta-value">BM25 + vector lanes</dd>
            </div>
            <div className="meta-item">
              <dt className="meta-key">Fusion</dt>
              <dd className="meta-value">Reciprocal rank fusion</dd>
            </div>
            <div className="meta-item">
              <dt className="meta-key">Contract</dt>
              <dd className="meta-value">Chunk-level receipts</dd>
            </div>
          </dl>
        </header>

        <section className="method-principles" aria-labelledby="principles-title">
          <header className="method-block-head">
            <p className="eyebrow">Structural principles</p>
            <h2 id="principles-title">Four commitments the archive keeps.</h2>
          </header>
          <div className="method-principles__grid">
            {PRINCIPLES.map((principle) => (
              <article className="principle-card" key={principle.index}>
                <span className="principle-card__num">
                  {principle.index} // {principle.eyebrow.toUpperCase()}
                </span>
                <h3 className="principle-card__title">{principle.title}</h3>
                <p className="principle-card__body">{principle.body}</p>
              </article>
            ))}
          </div>
        </section>

        <blockquote className="method-pullquote">
          <Icon name="quote" size={24} />
          <p>
            A path answers where. A timestamp answers when. Neither is sufficient alone.
          </p>
        </blockquote>

        <section
          className="method-section"
          id="two-libraries"
          aria-labelledby="two-libraries-title"
        >
          <header className="method-section__head">
            <span className="method-section__number">01</span>
            <div>
              <p className="eyebrow">Two shapes of provenance</p>
              <h2 id="two-libraries-title">
                A file is known by its path. A memory is known by its moment.
              </h2>
            </div>
          </header>
          <div className="method-prose">
            <p>
              Drop a file into <code>/history/industry/automobiles</code> and you have
              made two claims at once: it belongs here, and this is what it is called.
              The path is a retrievable coordinate. Every chunk of the file is indexed
              against it, and the original bytes stay untouched.
            </p>
            <p>
              A memory has no folder. It arrives in sequence, accumulates, and sometimes
              replaces an earlier belief. Saving a new memory can point at the entries it
              supersedes; those older entries become deprecated, leave the default search
              surface, and remain behind an explicit trace.
            </p>
            <p>
              The two libraries share one search index, one citation grammar, and one
              reading room. They differ in their geometry: a path is spatial, a timestamp
              is temporal.
            </p>
          </div>
          <FileVsMemoryDiagram />
        </section>

        <section
          className="method-section"
          id="hybrid-search"
          aria-labelledby="hybrid-title"
        >
          <header className="method-section__head">
            <span className="method-section__number">02</span>
            <div>
              <p className="eyebrow">Hybrid retrieval</p>
              <h2 id="hybrid-title">Two lanes in, one ranked set out.</h2>
            </div>
          </header>
          <div className="method-prose">
            <p>
              One index would be easier to explain and worse to use. A semantic query
              such as <em>when did my thinking about urban trees change?</em> needs
              vectors. A precise query such as <code>2026_automobile_history.md</code>{" "}
              needs literal matching. The archive asks both.
            </p>
            <p>
              BM25 runs over CJK bigrams, Latin word n-grams, and character trigrams.
              Cosine similarity runs over the configured embedding vectors. Each lane
              returns its own top N, two by default. The lanes merge through reciprocal
              rank fusion and deduplicate by source kind, source id, and chunk index, so
              a passage found by both routes rises naturally.
            </p>
            <p>
              The response is explicit about its own weather: <code>matched_by</code>,{" "}
              <code>text_candidates</code>, <code>vector_candidates</code>,{" "}
              <code>merged</code>, and <code>deduplicated</code>. You can audit the
              search, not just trust it.
            </p>
          </div>
          <HybridSearchDiagram />
          <aside className="method-note">
            <span className="method-note__marker" aria-hidden="true" />
            <div>
              <p className="eyebrow">Graceful degradation</p>
              <p>
                If embeddings are unavailable, the vector lane is skipped without
                blocking writes. If a bigram lookup finds nothing, unigram recall keeps
                the search from going dark. The response reports which lane answered.
              </p>
            </div>
          </aside>
        </section>

        <section
          className="method-section"
          id="citation-loop"
          aria-labelledby="citation-title"
        >
          <header className="method-section__head">
            <span className="method-section__number">03</span>
            <div>
              <p className="eyebrow">The citation contract</p>
              <h2 id="citation-title">The receipt is part of the answer.</h2>
            </div>
          </header>
          <div className="method-prose">
            <p>
              In a loose retrieval pipeline, passages arrive without provenance and the
              reader has no way to check which page supported a claim. Here a citation
              names both the source and the exact window that answered: chunk indexes
              start at one, and every searchable passage carries its source kind, source
              id, and chunk index.
            </p>
          </div>
          <ol className="method-loop">
            {CITATION_LOOP.map((step) => (
              <li className="method-loop__step" key={step.index}>
                <span className="method-loop__index">{step.index}</span>
                <div>
                  <h3>{step.title}</h3>
                  <p>{step.body}</p>
                </div>
              </li>
            ))}
          </ol>
          <p className="method-prose__closing">
            Summaries follow the same rule. A summary citation is shown inline with the
            answer because a summary has no separate room in this interface; the trace
            still points back to the record that produced it.
          </p>
        </section>

        <footer className="method-colophon">
          <div className="method-colophon__mark">
            <span className="shell-tag">Method</span>
            <p>Apsor Archive · The annual ring archive · Rev. 2026.10</p>
          </div>
          <nav className="method-colophon__links" aria-label="Archive links">
            <Link className="text-link" to="/dashboard">
              Dashboard
            </Link>
            <Link className="text-link" to="/questions">
              Questions
            </Link>
            <Link className="text-link" to="/settings">
              Settings
            </Link>
          </nav>
        </footer>
      </div>
    </div>
  );
}
