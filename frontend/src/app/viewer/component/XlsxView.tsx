import {
  lazy,
  Suspense,
  useEffect,
  useRef,
  useState,
  type KeyboardEvent,
} from "react";
import { useQuery } from "@tanstack/react-query";
import { read as readWorkbook, type ParsingOptions, type WorkBook } from "xlsx";

import { useI18n } from "../../i18n";
import { ChunkFallback } from "./ChunkFallback";
import { ViewerErrorState, ViewerLoading } from "./ViewerStates";
import {
  fetchViewerBinary,
  fileDownloadUrl,
  viewerErrorMessage,
  ViewerResourceError,
} from "./viewer-utils";

const XlsxGrid = lazy(() =>
  import("./XlsxGrid").then((module) => ({ default: module.XlsxGrid })),
);

interface XlsxViewProps {
  readonly fileId: number;
  readonly fileUrl: string;
  readonly fileName: string;
  readonly totalChunks: number;
}

/**
 * Parse options keep SheetJS to values only: no HTML strings, no styles, no
 * number-format metadata, no VBA, and no extra book parts. The dense cell
 * layout avoids one object per addressed cell on large sheets. `dateNF`
 * replaces the locale-dependent default date format with sortable ISO text;
 * midnight-only values are shortened again when the grid renders them.
 */
const XLSX_READ_OPTIONS: ParsingOptions = {
  type: "array",
  dense: true,
  cellDates: true,
  cellHTML: false,
  cellNF: false,
  cellStyles: false,
  bookVBA: false,
  bookProps: false,
  bookFiles: false,
  bookSheets: false,
  WTF: false,
  dateNF: "yyyy-mm-dd hh:mm:ss",
};

type ParseOutcome =
  | { readonly workbook: WorkBook; readonly error: null }
  | { readonly workbook: null; readonly error: unknown };

function parseWorkbook(buffer: ArrayBuffer): ParseOutcome {
  try {
    return {
      workbook: readWorkbook(new Uint8Array(buffer), XLSX_READ_OPTIONS),
      error: null,
    };
  } catch (error) {
    return { workbook: null, error };
  }
}

function tabDomId(fileId: number, index: number): string {
  return `viewer-xlsx-${fileId}-tab-${index}`;
}

function panelDomId(fileId: number): string {
  return `viewer-xlsx-${fileId}-panel`;
}

function isUnavailable(error: unknown): boolean {
  return error instanceof ViewerResourceError && error.status === 404;
}

/**
 * Spreadsheet preview. The workbook is parsed in the browser with SheetJS and
 * only the active sheet's first 500 rows and 50 columns reach the DOM. When the
 * original cannot be parsed, the indexed text stays reachable instead of
 * leaving a dead preview.
 */
export function XlsxView({
  fileId,
  fileUrl,
  fileName,
  totalChunks,
}: XlsxViewProps) {
  const { t } = useI18n();
  const [activeIndex, setActiveIndex] = useState(0);
  const [parsed, setParsed] = useState<ParseOutcome | null>(null);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  const binaryQuery = useQuery({
    queryKey: ["viewer", "file-binary", fileId],
    queryFn: ({ signal }) => fetchViewerBinary(fileUrl, signal),
    retry: false,
    staleTime: 5 * 60_000,
  });

  useEffect(() => {
    const buffer = binaryQuery.data;
    if (!buffer) {
      return;
    }
    let cancelled = false;
    // Yield one frame so the loading state paints before the synchronous
    // SheetJS parse starts; the parse itself still runs on the main thread.
    const timer = window.setTimeout(() => {
      if (!cancelled) {
        setParsed(parseWorkbook(buffer));
      }
    }, 0);
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [binaryQuery.data]);

  if (binaryQuery.isLoading || (binaryQuery.data !== undefined && parsed === null)) {
    return <ViewerLoading label={t("library.viewer.loading.xlsxOriginal")} />;
  }

  if (binaryQuery.error) {
    if (isUnavailable(binaryQuery.error) && totalChunks > 0) {
      return (
        <ChunkFallback
          fileId={fileId}
          totalChunks={totalChunks}
          reason={viewerErrorMessage(binaryQuery.error, t)}
        />
      );
    }
    return (
      <ViewerErrorState
        error={binaryQuery.error}
        title={t("library.viewer.xlsx.errorOriginal")}
        onRetry={() => void binaryQuery.refetch()}
        downloadUrl={fileDownloadUrl(fileId)}
        downloadName={fileName}
      />
    );
  }

  if (!parsed) {
    return null;
  }

  if (!parsed.workbook) {
    const reason = viewerErrorMessage(parsed.error, t);
    if (totalChunks > 0) {
      return (
        <ChunkFallback
          fileId={fileId}
          totalChunks={totalChunks}
          reason={t("library.viewer.xlsx.parseFallback", { reason })}
        />
      );
    }
    return (
      <ViewerErrorState
        error={parsed.error}
        title={t("library.viewer.xlsx.errorParse")}
        downloadUrl={fileDownloadUrl(fileId)}
        downloadName={fileName}
      />
    );
  }

  const workbook = parsed.workbook;
  const sheetNames = workbook.SheetNames;
  if (sheetNames.length === 0) {
    return <p className="viewer-empty">{t("library.viewer.xlsx.emptyWorkbook")}</p>;
  }

  const safeIndex = Math.min(Math.max(activeIndex, 0), sheetNames.length - 1);
  const sheetName = sheetNames[safeIndex];
  const sheet = workbook.Sheets[sheetName];
  if (!sheet) {
    return <p className="viewer-empty">{t("library.viewer.xlsx.empty")}</p>;
  }

  const selectSheet = (index: number) => {
    const bounded = (index + sheetNames.length) % sheetNames.length;
    setActiveIndex(bounded);
    tabRefs.current[bounded]?.focus();
  };

  const handleTabKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    index: number,
  ) => {
    if (event.key === "ArrowRight") {
      event.preventDefault();
      selectSheet(index + 1);
    } else if (event.key === "ArrowLeft") {
      event.preventDefault();
      selectSheet(index - 1);
    } else if (event.key === "Home") {
      event.preventDefault();
      selectSheet(0);
    } else if (event.key === "End") {
      event.preventDefault();
      selectSheet(sheetNames.length - 1);
    }
  };

  return (
    <div className="viewer-xlsx">
      <div className="viewer-xlsx__bar">
        <div
          className="viewer-xlsx__tabs"
          role="tablist"
          aria-label={t("library.viewer.xlsx.sheetTabs")}
        >
          {sheetNames.map((name, index) => {
            const selected = index === safeIndex;
            return (
              <button
                key={name}
                type="button"
                role="tab"
                id={tabDomId(fileId, index)}
                className="viewer-xlsx__tab"
                aria-selected={selected}
                aria-controls={panelDomId(fileId)}
                tabIndex={selected ? 0 : -1}
                ref={(node) => {
                  tabRefs.current[index] = node;
                }}
                onClick={() => setActiveIndex(index)}
                onKeyDown={(event) => handleTabKeyDown(event, index)}
              >
                <span className="viewer-xlsx__tab-label">{name}</span>
                {workbook.Workbook?.Sheets?.[index]?.Hidden ? (
                  <span className="viewer-xlsx__hidden">
                    {t("library.viewer.xlsx.hidden")}
                  </span>
                ) : null}
              </button>
            );
          })}
        </div>
      </div>
      <Suspense
        fallback={<ViewerLoading label={t("library.viewer.loading.xlsxLayout")} />}
      >
        <XlsxGrid
          sheet={sheet}
          panelId={panelDomId(fileId)}
          tabId={tabDomId(fileId, safeIndex)}
        />
      </Suspense>
    </div>
  );
}
