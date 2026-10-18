import { useMemo } from "react";

import { formatNumber } from "../../../lib/format";
import { parseCsv } from "./viewer-utils";

interface CsvSheetProps {
  readonly content: string;
  readonly wrap: boolean;
}

/** A bounded, read-only CSV sheet with a sticky header and row numbers. */
export function CsvSheet({ content, wrap }: CsvSheetProps) {
  const table = useMemo(() => parseCsv(content), [content]);

  if (table.headers.length === 0) {
    return <p className="viewer-empty">This CSV file has no rows.</p>;
  }

  return (
    <div className="viewer-csv">
      <div className="viewer-csv__scroll" tabIndex={0}>
        <table className={wrap ? "viewer-csv__table is-wrapped" : "viewer-csv__table"}>
          <thead>
            <tr>
              <th scope="col" className="viewer-csv__index">
                #
              </th>
              {table.headers.map((header, index) => (
                <th scope="col" key={`header-${index}`}>
                  {header.trim().length > 0 ? header : `Column ${index + 1}`}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {table.rows.map((row, rowIndex) => (
              <tr key={`row-${rowIndex}`}>
                <th scope="row" className="viewer-csv__index">
                  {rowIndex + 1}
                </th>
                {table.headers.map((_, columnIndex) => (
                  <td key={`cell-${rowIndex}-${columnIndex}`}>
                    {row[columnIndex] ?? ""}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="viewer-csv__note">
        {formatNumber(table.rows.length)} of {formatNumber(table.totalRows)} rows
        {table.truncated ? " shown (bounded preview)" : ""}. Quoted commas and line breaks
        are preserved.
      </p>
    </div>
  );
}
