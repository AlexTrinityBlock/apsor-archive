import type {
  ListResponseSchemaMediaSchema,
  MediaSchema,
  MediaSearchResponseSchema,
} from "../../generated-apis-types/schemas";
import { Button } from "../../component/Button";
import { Panel } from "../../component/Panel";
import { QueryState } from "../../component/QueryState";
import { MediaEmptyArchive, MediaNoResults } from "./MediaEmptyState";
import { MediaGallery } from "./MediaGallery";
import { MediaPager } from "./MediaPager";

export type MediaArchiveMode = "archive" | "text" | "visual";

interface ResultActions {
  readonly onClearText: () => void;
  readonly onClearImage: () => void;
  readonly onAddImage: () => void;
  readonly onSelect: (media: MediaSchema) => void;
}

interface MediaArchiveStatesProps extends ResultActions {
  readonly mode: MediaArchiveMode;
  readonly query: string;
  readonly offset: number;
  readonly pageSize: number;
  readonly textResults?: MediaSearchResponseSchema;
  readonly textLoading: boolean;
  readonly textError: unknown;
  readonly imageResults?: MediaSearchResponseSchema;
  readonly imageLoading: boolean;
  readonly imageError: unknown;
  readonly listing?: ListResponseSchemaMediaSchema;
  readonly listingLoading: boolean;
  readonly listingError: unknown;
  readonly onOffsetChange: (offset: number) => void;
}

function TextResults({
  results,
  query,
  onClearText,
  onAddImage,
  onSelect,
}: Pick<ResultActions, "onClearText" | "onAddImage" | "onSelect"> & {
  readonly results?: MediaSearchResponseSchema;
  readonly query: string;
}) {
  if (!results) {
    return null;
  }
  if (results.results.length === 0) {
    return (
      <MediaNoResults
        mode="text"
        query={query}
        onClear={onClearText}
        onAddImage={onAddImage}
      />
    );
  }
  return (
    <MediaGallery
      items={results.results}
      total={results.total}
      mode="text"
      query={query}
      elapsedMs={results.elapsed_ms}
      onSelect={onSelect}
    />
  );
}

function VisualResults({
  results,
  onClearImage,
  onAddImage,
  onSelect,
}: Pick<ResultActions, "onClearImage" | "onAddImage" | "onSelect"> & {
  readonly results?: MediaSearchResponseSchema;
}) {
  if (!results) {
    return null;
  }
  if (results.results.length === 0) {
    return (
      <MediaNoResults
        mode="visual"
        onClear={onClearImage}
        onAddImage={onAddImage}
      />
    );
  }
  return (
    <MediaGallery
      items={results.results}
      total={results.total}
      mode="visual"
      elapsedMs={results.elapsed_ms}
      onSelect={onSelect}
    />
  );
}

function ArchiveResults({
  listing,
  offset,
  pageSize,
  onSelect,
  onOffsetChange,
}: Pick<ResultActions, "onSelect"> & {
  readonly listing?: ListResponseSchemaMediaSchema;
  readonly offset: number;
  readonly pageSize: number;
  readonly onOffsetChange: (offset: number) => void;
}) {
  if (!listing) {
    return null;
  }
  if (listing.resources.length === 0) {
    return (
      <Panel tone="plain" className="media-sheet-empty reveal reveal-3">
        <p className="eyebrow">Empty sheet</p>
        <h2>No specimens on this sheet.</h2>
        <p>The archive changed while you were reading. Return to the first sheet.</p>
        <Button variant="secondary" size="sm" onClick={() => onOffsetChange(0)}>
          Back to the first sheet
        </Button>
      </Panel>
    );
  }
  return (
    <>
      <MediaGallery
        items={listing.resources}
        total={listing.total_results}
        mode="archive"
        onSelect={onSelect}
      />
      <MediaPager
        offset={offset}
        pageSize={pageSize}
        total={listing.total_results}
        onOffsetChange={onOffsetChange}
      />
    </>
  );
}

/**
 * Chooses the active result surface: text-to-image matches, image-to-image
 * neighbours, or the paginated specimen archive. Each branch keeps its own
 * loading and API-error detail inside QueryState.
 */
export function MediaArchiveStates({
  mode,
  query,
  offset,
  pageSize,
  textResults,
  textLoading,
  textError,
  imageResults,
  imageLoading,
  imageError,
  listing,
  listingLoading,
  listingError,
  onClearText,
  onClearImage,
  onAddImage,
  onSelect,
  onOffsetChange,
}: MediaArchiveStatesProps) {
  if (mode === "text") {
    return (
      <QueryState
        loading={textLoading}
        error={textError}
        loadingLabel="Searching captions, OCR, and tags"
      >
        <TextResults
          results={textResults}
          query={query}
          onClearText={onClearText}
          onAddImage={onAddImage}
          onSelect={onSelect}
        />
      </QueryState>
    );
  }

  if (mode === "visual") {
    return (
      <QueryState
        loading={imageLoading}
        error={imageError}
        loadingLabel="Comparing visual fingerprints"
      >
        <VisualResults
          results={imageResults}
          onClearImage={onClearImage}
          onAddImage={onAddImage}
          onSelect={onSelect}
        />
      </QueryState>
    );
  }

  return (
    <QueryState
      loading={listingLoading}
      error={listingError}
      empty={listing?.total_results === 0}
      emptyState={<MediaEmptyArchive onAddImage={onAddImage} />}
      loadingLabel="Reading the media index"
    >
      <ArchiveResults
        listing={listing}
        offset={offset}
        pageSize={pageSize}
        onSelect={onSelect}
        onOffsetChange={onOffsetChange}
      />
    </QueryState>
  );
}
