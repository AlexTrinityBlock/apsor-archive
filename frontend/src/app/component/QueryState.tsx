import type { ReactNode } from "react";

import { Loader } from "./Loader";
import { Panel } from "./Panel";

interface QueryStateProps {
  readonly loading: boolean;
  readonly error: unknown;
  readonly empty?: boolean;
  readonly emptyState?: ReactNode;
  readonly loadingLabel?: string;
  readonly children: ReactNode;
}

function errorMessage(error: unknown): string {
  if (error instanceof Error) {
    return error.message;
  }
  if (typeof error === "string") {
    return error;
  }
  return "The archive could not be read.";
}

/** A consistent loading / failure / empty frame for data-backed panels. */
export function QueryState({
  loading,
  error,
  empty = false,
  emptyState,
  loadingLabel = "Reading the archive",
  children,
}: QueryStateProps) {
  if (loading) {
    return (
      <Panel tone="plain" className="query-state">
        <div className="query-state__loading">
          <Loader label={loadingLabel} />
        </div>
      </Panel>
    );
  }
  if (error) {
    return (
      <Panel tone="plain" className="query-state query-state--error">
        <p className="eyebrow">Read interrupted</p>
        <h2>The archive did not answer.</h2>
        <p className="query-state__detail">{errorMessage(error)}</p>
      </Panel>
    );
  }
  if (empty) {
    return <>{emptyState}</>;
  }
  return <>{children}</>;
}
