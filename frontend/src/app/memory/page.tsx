import { useParams } from "react-router-dom";

import { MemoryMissing } from "./component/MemoryMissing";
import { MemoryNewView } from "./component/MemoryNewView";
import { MemoryReadView } from "./component/MemoryReadView";
import { parseMemoryId } from "./component/helpers";
import "./memory.css";

/**
 * Memory route: `/memory/new` opens the pressing room, while
 * `/memory/:memoryId` reads one record with its full history.
 */
export function MemoryPage() {
  const { memoryId } = useParams<{ memoryId: string }>();

  if (memoryId === "new") {
    return <MemoryNewView />;
  }

  const parsedId = parseMemoryId(memoryId);
  if (parsedId === null) {
    return <MemoryMissing memoryId={memoryId} invalid />;
  }

  return <MemoryReadView memoryId={parsedId} />;
}
