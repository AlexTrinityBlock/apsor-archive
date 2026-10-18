import { useRef, useState, type ChangeEvent } from "react";
import { useLocation } from "react-router-dom";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { SearchField } from "../../component/SearchField";
import { MEDIA_ACCEPT } from "./media-utils";

export interface ImageQueryPreview {
  readonly name: string;
  readonly previewUrl: string;
}

interface MediaToolbarProps {
  readonly activeQuery: string;
  readonly resetToken: number;
  readonly onSearch: (value: string) => void;
  readonly onClearSearch: () => void;
  readonly onSearchByImage: (file: File) => void;
  readonly onClearImageSearch: () => void;
  readonly imageQuery: ImageQueryPreview | null;
  readonly imageSearching: boolean;
  readonly imageSearchError: string | null;
  readonly onAddImage: () => void;
}

interface SearchStatusProps {
  readonly draftQuery: string;
  readonly activeQuery: string;
  readonly onClearSearch: () => void;
}

function SearchStatus({ draftQuery, activeQuery, onClearSearch }: SearchStatusProps) {
  if (activeQuery) {
    return (
      <>
        <span className="eyebrow">Text search</span>
        <code>“{activeQuery}”</code>
        <Button variant="ghost" size="sm" onClick={onClearSearch}>
          Clear
        </Button>
      </>
    );
  }
  if (draftQuery.trim().length > 0) {
    return (
      <>
        <span className="media-toolbar__reading">Press Enter to search the media index.</span>
        <Button variant="ghost" size="sm" onClick={onClearSearch}>
          Clear
        </Button>
      </>
    );
  }
  return <span>Search captions, OCR text, and tags across the visual index.</span>;
}

/**
 * The visual archive's command strip: text-to-image search, a hidden
 * image-to-image picker, and the intake button. The query image stays visible
 * so the search mode is never ambiguous.
 */
export function MediaToolbar({
  activeQuery,
  resetToken,
  onSearch,
  onClearSearch,
  onSearchByImage,
  onClearImageSearch,
  imageQuery,
  imageSearching,
  imageSearchError,
  onAddImage,
}: MediaToolbarProps) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const location = useLocation();
  // Location keys make a history round-trip back to the same query a distinct
  // source, so a typed draft cannot reappear after back/forward.
  const source = `${location.key}:${activeQuery}:${resetToken}`;
  const [draftState, setDraftState] = useState({ source, value: activeQuery });
  // The URL (and the reset token) remains authoritative. A source mismatch
  // means external state changed; render that value without an effect.
  const draftQuery = draftState.source === source ? draftState.value : activeQuery;

  const updateDraft = (value: string) => {
    setDraftState({ source, value });
  };

  const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0] ?? null;
    event.target.value = "";
    if (file) {
      onSearchByImage(file);
    }
  };

  const handleClear = () => {
    updateDraft("");
    onClearSearch();
  };

  return (
    <section className="media-toolbar reveal reveal-2" aria-label="Search and add media">
      <div className="media-toolbar__search">
        <SearchField
          value={draftQuery}
          onChange={updateDraft}
          onSubmit={onSearch}
          label="Search image captions, OCR text, and tags"
          placeholder="Search captions, OCR, tags…"
          submitLabel="Search"
        />
        <div className="media-toolbar__status" aria-live="polite">
          <SearchStatus
            draftQuery={draftQuery}
            activeQuery={activeQuery}
            onClearSearch={handleClear}
          />
        </div>
        {imageSearchError ? (
          <p className="media-toolbar__error" role="alert">
            <Icon name="info" size={15} />
            <span>{imageSearchError}</span>
          </p>
        ) : null}
      </div>

      <div className="media-toolbar__actions">
        <input
          ref={fileInputRef}
          type="file"
          accept={MEDIA_ACCEPT}
          onChange={handleFileChange}
          className="visually-hidden"
          tabIndex={-1}
          aria-hidden="true"
        />
        <Button
          variant="secondary"
          size="sm"
          onClick={() => fileInputRef.current?.click()}
          disabled={imageSearching}
        >
          <Icon name="search" size={15} />
          {imageSearching ? "Comparing…" : "Search by image"}
        </Button>
        <Button variant="primary" size="sm" onClick={onAddImage}>
          <Icon name="plus" size={15} />
          Add image
        </Button>
      </div>

      {imageQuery ? (
        <div className="media-query" aria-live="polite" aria-busy={imageSearching}>
          <div className="media-query__thumb">
            <img src={imageQuery.previewUrl} alt={`Search query image: ${imageQuery.name}`} />
          </div>
          <div className="media-query__copy">
            <p className="eyebrow">Image query · visual similarity</p>
            <code>{imageQuery.name}</code>
            <p>
              {imageSearching
                ? "Comparing visual fingerprints across the archive."
                : "Ranked by visual similarity, independent of captions and OCR."}
            </p>
          </div>
          <Badge tone="ochre" dot>
            Visual similarity
          </Badge>
          <Button variant="ghost" size="sm" onClick={onClearImageSearch}>
            <Icon name="close" size={14} />
            Clear image
          </Button>
        </div>
      ) : null}
    </section>
  );
}
