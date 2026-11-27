import { useNavigate } from "react-router-dom";

import {
  libraryFolderUrl,
  libraryMemoriesUrl,
  type LibraryMemoryRoute,
} from "../../../lib/library-url";
import { useI18n } from "../../i18n";
import {
  LibraryTabStrip,
  libraryTabId,
  type LibraryCollection,
} from "../component/LibraryTabStrip";
import { MemoryMissing } from "./component/MemoryMissing";
import { MemoryNewView } from "./component/MemoryNewView";
import { MemoryReadView } from "./component/MemoryReadView";
import { MemoryVault } from "./component/MemoryVault";
import { parseMemoryId } from "./component/helpers";
import "./memory.css";

/**
 * The Library's Memories collection: `/library/memories` is the index,
 * `/library/memories/new` the new-memory form, and `/library/memories/:id`
 * reads one record with its related memories and history. Memories have no
 * folders, so there is no breadcrumb or file toolbar here. The Library page is
 * fixed-height, so the memory canvas owns its own scroll.
 */
export function LibraryMemoryWorkspace({
  route,
}: {
  readonly route: LibraryMemoryRoute;
}) {
  const { t } = useI18n();
  const navigate = useNavigate();

  const selectCollection = (collection: LibraryCollection) => {
    if (collection === "memories") {
      if (route.kind !== "index") {
        navigate(libraryMemoriesUrl());
      }
      return;
    }
    navigate(libraryFolderUrl("/", collection));
  };

  return (
    <div className="library-page library-page--memories">
      <h1 className="visually-hidden">{t("library.page.title")}</h1>
      <header className="library-topbar library-topbar--memories">
        <div className="library-viewstrip">
          <LibraryTabStrip active="memories" onSelect={selectCollection} />
        </div>
      </header>
      <div
        className="library-canvas library-canvas--memories"
        id="library-panel"
        role="tabpanel"
        aria-labelledby={libraryTabId("memories")}
      >
        <MemoryRoute route={route} />
      </div>
    </div>
  );
}

function MemoryRoute({ route }: { readonly route: LibraryMemoryRoute }) {
  if (route.kind === "index") {
    return <MemoryVault />;
  }
  if (route.kind === "new") {
    return <MemoryNewView />;
  }
  const parsedId = parseMemoryId(route.rawId);
  if (parsedId === null) {
    return <MemoryMissing memoryId={route.rawId} invalid />;
  }
  return <MemoryReadView key={parsedId} memoryId={parsedId} />;
}
