import { ButtonLink } from "../component/Button";
import { Icon } from "../component/Icon";
import { TreeRings } from "../component/TreeRings";
import { ChunkMapDiagram } from "./component/ChunkMapDiagram";
import { FileVsMemoryDiagram } from "./component/FileVsMemoryDiagram";
import { HybridSearchDiagram } from "./component/HybridSearchDiagram";
import { LineageDiagram } from "./component/LineageDiagram";
import { RagFlowDiagram } from "./component/RagFlowDiagram";
import { TimelineSamplingDiagram } from "./component/TimelineSamplingDiagram";

const CONTENTS = [
  { id: "two-libraries", index: "01", label: "Two libraries" },
  { id: "versions", index: "02", label: "Versions branch" },
  { id: "hybrid-search", index: "03", label: "Two searches" },
  { id: "timeline-sampling", index: "04", label: "Five anchors" },
  { id: "tree-and-chunks", index: "05", label: "One tree" },
  { id: "answers", index: "06", label: "Receipts" },
  { id: "limits", index: "07", label: "Blank space" },
] as const;

/**
 * The method essay: an editorial explanation of the archive's two libraries,
 * the retrieval geometry, the sparse timeline, and the citation contract.
 */
export function MethodPage() {
  return (
    <div className="page method-page">
      <header className="method-hero">
        <div className="method-hero__rings" aria-hidden="true">
          <TreeRings variant="quiet" />
        </div>
        <div className="method-hero__kicker reveal reveal-1">
          <span className="eyebrow">Method · field notes</span>
          <span className="hairline" aria-hidden="true" />
          <span className="eyebrow">Rev. 2026.10</span>
        </div>
        <h1 className="method-hero__title reveal reveal-2">
          Two libraries.
          <span>One <em>tree.</em></span>
        </h1>
        <div className="method-hero__base reveal reveal-3">
          <p className="method-hero__lede">
            Most knowledge tools flatten a library into a list. DendroMatrix keeps two
            shapes — the branching path of files and the linear grain of memory — then
            folds both into a single, citable index.
          </p>
          <dl className="method-meta">
            <div>
              <dt>Archive</dt>
              <dd>Files, memories, summaries</dd>
            </div>
            <div>
              <dt>Retrieval</dt>
              <dd>BM25 + hashing vectors</dd>
            </div>
            <div>
              <dt>Fusion</dt>
              <dd>Reciprocal rank fusion</dd>
            </div>
            <div>
              <dt>Reading time</dt>
              <dd>9 minutes · 6 figures</dd>
            </div>
          </dl>
        </div>
      </header>

      <div className="method-layout">
        <aside className="method-toc" aria-label="Essay contents">
          <p className="eyebrow">Contents</p>
          <nav aria-label="Sections">
            <ol>
              {CONTENTS.map((entry) => (
                <li key={entry.id}>
                  <a href={`#${entry.id}`}>
                    <span>{entry.index}</span>
                    {entry.label}
                  </a>
                </li>
              ))}
            </ol>
          </nav>
          <div className="method-toc__note">
            <Icon name="ring" size={18} />
            <p>Six figures. One archive.</p>
          </div>
        </aside>

        <article className="method-essay">
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
                  A file is known by its path.
                  <br />
                  A memory is known by its moment.
                </h2>
              </div>
            </header>
            <div className="method-prose has-dropcap">
              <p>
                Drop a PDF into <code>/history/industry/automobiles</code> and you have
                made two claims at once: it belongs here, and this is what it is called.
                The path is not decoration; it is a retrievable coordinate. Every chunk
                of every file is indexed against it.
              </p>
              <p>
                A memory has no folder. It arrives in sequence, accumulates, and
                sometimes replaces an earlier belief. The Memory Library gives every
                entry its own <code>memory_id</code> and <code>memory_time</code>. Saving
                a new memory can point at the ones it supersedes; those older entries
                become <code>deprecated</code>, leave the default search surface, and
                remain forever behind an explicit trace.
              </p>
              <p>
                The two libraries share one search index, one citation grammar, and one
                reading room. They differ in their geometry.
              </p>
            </div>
            <FileVsMemoryDiagram />
            <blockquote className="method-pullquote">
              <Icon name="quote" size={26} />
              <p>A path answers where. A timestamp answers when. Neither is sufficient alone.</p>
            </blockquote>
          </section>

          <section className="method-section" id="versions" aria-labelledby="versions-title">
            <header className="method-section__head">
              <span className="method-section__number">02</span>
              <div>
                <p className="eyebrow">Lineage</p>
                <h2 id="versions-title">Versions are branches, not overwrites.</h2>
              </div>
            </header>
            <div className="method-prose">
              <p>
                Re-uploading a file at the same path is a normal act, not an error to be
                deduplicated. DendroMatrix treats it as a new edition. The old file, tree
                node, and chunks are marked non-current; the new records receive new ids.
                Ids are never reused, even after a soft delete.
              </p>
              <p>
                The default tree shows current leaves only. <code>include_history=true</code>{" "}
                reveals the old branches in low contrast. Search follows current chunks;{" "}
                <code>read_memory</code> follows supersede chains. History is available,
                but it does not contaminate the present unless asked.
              </p>
            </div>
            <LineageDiagram />
            <aside className="method-note">
              <span className="method-note__marker" aria-hidden="true" />
              <div>
                <p className="eyebrow">No destructive edit</p>
                <p>
                  A deleted file is a closed branch. Its identifiers remain spent, its
                  trace remains legible, and a future upload cannot inherit its history.
                </p>
              </div>
            </aside>
            <div className="metric-ribbon" aria-label="Version lineage in numbers">
              <div><strong>3</strong><span>editions</span></div>
              <div><strong>12</strong><span>old chunks kept</span></div>
              <div><strong>189</strong><span>current chunks</span></div>
              <div><strong>0</strong><span>ids reused</span></div>
            </div>
          </section>

          <section
            className="method-section"
            id="hybrid-search"
            aria-labelledby="hybrid-title"
          >
            <header className="method-section__head">
              <span className="method-section__number">03</span>
              <div>
                <p className="eyebrow">Hybrid retrieval</p>
                <h2 id="hybrid-title">2 + 2, then subtract once.</h2>
              </div>
            </header>
            <div className="method-prose">
              <p>
                One index would be easier to explain and worse to use. A semantic query —
                <em> when did my thinking about urban trees change?</em> — needs vectors. A
                precise query — <code>2026_automobile_history.md</code> — needs literal
                matching. The archive asks both.
              </p>
              <p>
                BM25 runs over CJK bigrams, Latin word n-grams, and character trigrams.
                Cosine similarity runs over hashing embeddings. Each lane returns its own
                top N, two by default. The lanes merge through reciprocal rank fusion and
                deduplicate by source kind, source id, and chunk index. A passage found by
                both routes naturally rises.
              </p>
              <p>
                The response is explicit about its own weather: <code>matched_by</code>,{" "}
                <code>text_candidates</code>, <code>vector_candidates</code>,{" "}
                <code>merged</code>, <code>deduplicated</code>. You can audit the search,
                not just trust it.
              </p>
            </div>
            <HybridSearchDiagram />
            <div className="metric-ribbon metric-ribbon--search" aria-label="Search fusion fields">
              <div><strong>2</strong><span>text candidates</span></div>
              <div><strong>2</strong><span>vector candidates</span></div>
              <div><strong>2</strong><span>per source kind</span></div>
              <div><strong>1/(60+rank)</strong><span>fusion weight</span></div>
            </div>
            <aside className="method-note method-note--wide">
              <span className="method-note__marker" aria-hidden="true" />
              <div>
                <p className="eyebrow">Graceful degradation</p>
                <p>
                  If embeddings are unavailable, the vector lane is skipped without
                  blocking writes. If no bigram matches, unigram recall keeps the search
                  from going dark. The archive reports the lane it used.
                </p>
              </div>
            </aside>
          </section>

          <section
            className="method-section"
            id="timeline-sampling"
            aria-labelledby="timeline-title"
          >
            <header className="method-section__head">
              <span className="method-section__number">04</span>
              <div>
                <p className="eyebrow">Timeline</p>
                <h2 id="timeline-title">Five anchors are enough to hear the season.</h2>
              </div>
            </header>
            <div className="method-prose">
              <p>
                A year of daily memories could return thousands of events. Loading all of
                them hides the shape. <code>read_timeline</code> samples five anchors
                across the requested range and chooses the nearest unseen event of each
                type: memories, summaries, and file changes. Each type contributes at
                most five events.
              </p>
              <p>
                The gaps are not discarded. <code>skips</code> counts what sits between
                adjacent visible events; <code>density</code> gives a day-by-day count for
                the miniature bars. An empty range returns an empty list, not an error.
                Absence is a fact worth returning.
              </p>
            </div>
            <TimelineSamplingDiagram />
            <blockquote className="method-pullquote method-pullquote--small">
              <Icon name="quote" size={22} />
              <p>The gaps are data too.</p>
            </blockquote>
          </section>

          <section
            className="method-section"
            id="tree-and-chunks"
            aria-labelledby="tree-title"
          >
            <header className="method-section__head">
              <span className="method-section__number">05</span>
              <div>
                <p className="eyebrow">The unified index</p>
                <h2 id="tree-title">One tree, three kinds of leaves.</h2>
              </div>
            </header>
            <div className="method-prose">
              <p>
                The <code>tree_node</code> table is one tree for folders, files, and their
                history. Every current file leaf points at a current file record.
                Separately, every searchable passage lives in one <code>chunk</code> table
                where <code>source_kind</code> is <code>file</code>, <code>memory</code>,
                or <code>summary</code>. The same BM25 and vector machinery serves all
                three.
              </p>
              <p>
                Chunks are 1-based and built to roughly 800 characters with up to 120
                characters of overlap. The original file is never mutated. A chunk cites
                its source id and chunk index, which is exactly what a citation needs:{" "}
                <code>file:12#15</code>.
              </p>
              <p>
                A summary is not a fourth exotic object. It is a{" "}
                <code>memory_summary</code> row and a chunk with{" "}
                <code>source_kind=summary</code>. It can be found, cited, and sampled on
                the timeline like anything else.
              </p>
            </div>
            <ChunkMapDiagram />
            <div className="source-notes" aria-label="Source kinds">
              <div>
                <span className="figure-label">file</span>
                <p>Original bytes preserved. Chunks carry a window into a versioned leaf.</p>
              </div>
              <div>
                <span className="figure-label">memory</span>
                <p>Active entries search. Deprecated entries wait behind an explicit trace.</p>
              </div>
              <div>
                <span className="figure-label">summary</span>
                <p>AI or extractive. The generator is part of the record, not a footnote.</p>
              </div>
            </div>
          </section>

          <section className="method-section" id="answers" aria-labelledby="answers-title">
            <header className="method-section__head">
              <span className="method-section__number">06</span>
              <div>
                <p className="eyebrow">Answering</p>
                <h2 id="answers-title">An answer without a citation is a rumour.</h2>
              </div>
            </header>
            <div className="method-prose">
              <p>
                Ask runs the same hybrid retrieval as search, then hands the selected
                passages to DeepSeek with a strict instruction: answer only from these
                excerpts, cite <code>[file:12#15]</code> or <code>[memory:1015]</code>,
                and return the sources. Without an API key the endpoint returns{" "}
                <code>503 ai_not_configured</code> rather than inventing prose.
              </p>
              <p>
                Summaries use the same discipline. DeepSeek produces a 2–4 sentence
                Traditional Chinese summary and themes as JSON; if the model is
                unavailable or the JSON is malformed, an extractive fallback selects
                representative memories and records{" "}
                <code>generator: extractive</code>. Every summary is chunked, searchable,
                and honest about which generator spoke.
              </p>
              <p>
                The citation is not a decorative footer. It is the difference between a
                memory archive and a confident stranger.
              </p>
            </div>
            <RagFlowDiagram />
          </section>

          <section className="method-section" id="limits" aria-labelledby="limits-title">
            <header className="method-section__head">
              <span className="method-section__number">07</span>
              <div>
                <p className="eyebrow">Constraints</p>
                <h2 id="limits-title">The blank space is part of the drawing.</h2>
              </div>
            </header>
            <div className="method-prose">
              <p>
                This is a single-reader, self-hosted archive bound to{" "}
                <code>127.0.0.1</code>. No accounts, no multi-tenant isolation, no
                background workers. PDFs are text-extracted; scanned pages wait outside
                the gate. Embeddings default to a deterministic hashing embedder. Exact
                cosine is fast enough at personal scale and leaves the Protocol open for
                pgvector later.
              </p>
              <p>
                These are not omissions to apologise for. They are the conditions that
                make a small, legible system possible.
              </p>
            </div>
            <div className="scope-grid">
              <div className="scope-card">
                <p className="eyebrow">Kept inside</p>
                <ul>
                  <li><Icon name="check" size={15} /> Local paths and soft lineage</li>
                  <li><Icon name="check" size={15} /> Hybrid retrieval with counts</li>
                  <li><Icon name="check" size={15} /> Citations and generator records</li>
                  <li><Icon name="check" size={15} /> Deterministic fallbacks</li>
                </ul>
              </div>
              <div className="scope-card scope-card--muted">
                <p className="eyebrow">Left outside</p>
                <ul>
                  <li><Icon name="close" size={15} /> Accounts and multi-tenancy</li>
                  <li><Icon name="close" size={15} /> OCR and media parsing</li>
                  <li><Icon name="close" size={15} /> Approximate nearest-neighbour search</li>
                  <li><Icon name="close" size={15} /> Background ingestion workers</li>
                </ul>
              </div>
            </div>
            <div className="method-signoff">
              <div>
                <p className="eyebrow">End of field notes</p>
                <p>DendroMatrix · The annual ring archive · Rev. 2026.10</p>
              </div>
              <div className="method-signoff__actions">
                <ButtonLink to="/ask" variant="ink" size="sm">
                  Ask the archive
                  <Icon name="arrow-up-right" size={15} />
                </ButtonLink>
                <ButtonLink to="/settings" variant="ghost" size="sm">
                  System settings
                  <Icon name="arrow-right" size={15} />
                </ButtonLink>
              </div>
            </div>
          </section>
        </article>
      </div>
    </div>
  );
}
