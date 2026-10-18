import { Badge } from "../../component/Badge";

const CHUNKS = [
  { kind: "file", source: "12", index: "15", citation: "file:12#15" },
  { kind: "memory", source: "1015", index: "1", citation: "memory:1015#1" },
  { kind: "summary", source: "96", index: "2", citation: "summary:96#2" },
] as const;

/** Figure 05: the tree locates a source; the chunk table makes it searchable. */
export function ChunkMapDiagram() {
  return (
    <figure className="method-figure">
      <div className="chunk-map">
        <div className="chunk-map__tree">
          <div className="chunk-map__tree-head">
            <span className="figure-label">tree_node</span>
            <Badge tone="moss">One tree</Badge>
          </div>
          <div className="tree-schema" aria-label="Unified tree nodes">
            <div className="tree-schema__row depth-0">
              <span className="tree-schema__glyph" aria-hidden="true" />
              <span>/history</span>
              <span>folder</span>
            </div>
            <div className="tree-schema__row depth-1">
              <span className="tree-schema__glyph" aria-hidden="true" />
              <span>/industry</span>
              <span>folder</span>
            </div>
            <div className="tree-schema__row depth-2 is-file">
              <span className="tree-schema__glyph" aria-hidden="true" />
              <span>2026_automobile_history.md</span>
              <span>file 12</span>
            </div>
            <div className="tree-schema__row depth-2 is-history">
              <span className="tree-schema__glyph" aria-hidden="true" />
              <span>2022_automobile_annual.md</span>
              <span>file 11</span>
            </div>
          </div>
          <p className="chunk-map__tree-note">
            Current leaves point at a current file. Old leaves stay as dashed history.
          </p>
        </div>

        <div className="chunk-map__chunks">
          <div className="chunk-map__tree-head">
            <span className="figure-label">chunk</span>
            <Badge tone="ochre">One index</Badge>
          </div>
          <table className="chunk-table">
            <caption className="visually-hidden">
              Example chunks from three source kinds sharing one index
            </caption>
            <thead>
              <tr>
                <th scope="col">source_kind</th>
                <th scope="col">source_id</th>
                <th scope="col">chunk</th>
                <th scope="col">is_current</th>
                <th scope="col">citation</th>
              </tr>
            </thead>
            <tbody>
              {CHUNKS.map((chunk) => (
                <tr key={chunk.citation}>
                  <td>{chunk.kind}</td>
                  <td>{chunk.source}</td>
                  <td>{chunk.index}</td>
                  <td>
                    <span className="status-yes">true</span>
                  </td>
                  <td>
                    <code>{chunk.citation}</code>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="chunk-map__chunks-note">
            Chunk indexes start at 1. A citation names both the source and the window
            that answered.
          </p>
        </div>
      </div>
      <figcaption>
        Figure 05 — Two tables, one address space. The tree makes provenance
        navigable; the chunk index makes every passage retrievable.
      </figcaption>
    </figure>
  );
}
