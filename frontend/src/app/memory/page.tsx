import { useLocation, useParams } from "react-router-dom";

import { MemoryMissing } from "./component/MemoryMissing";
import { MemoryNewView } from "./component/MemoryNewView";
import { MemoryReadView } from "./component/MemoryReadView";
import { MemoryVault } from "./component/MemoryVault";
import { parseMemoryId } from "./component/helpers";
import "./memory.css";

/**
 * Memory workspaces: `/memory` is the vault index, `/memory/new` is the
 * pressing room, and `/memory/:memoryId` reads one record with its history.
 */
export function MemoryPage() {
  const { memoryId } = useParams<{ memoryId: string }>();
  const location = useLocation();
  const pathSegments = location.pathname.split("/").filter(Boolean);
  const pathId =
    pathSegments.at(-2) === "memory" ? pathSegments.at(-1) : undefined;
  const routeId = memoryId ?? pathId;

  if (!routeId) {
    return <MemoryVault />;
  }

  if (routeId === "new") {
    return <MemoryNewView />;
  }

  const parsedId = parseMemoryId(routeId);
  if (parsedId === null) {
    return <MemoryMissing memoryId={routeId} invalid />;
  }

  return <MemoryReadView memoryId={parsedId} />;
}
