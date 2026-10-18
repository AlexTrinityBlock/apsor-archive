import { useCallback, useEffect, useRef, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";

import "./media.css";

import type { MediaSchema } from "../generated-apis-types/schemas";
import {
  useListMedia,
  useSearchMedia,
  useSearchMediaByImage,
} from "../generated-apis-types/media/media";
import { Badge } from "../component/Badge";
import { Button } from "../component/Button";
import { Icon } from "../component/Icon";
import { PageHeader } from "../component/PageHeader";
import { useToast } from "../component/Toast";
import {
  MediaArchiveStates,
  type MediaArchiveMode,
} from "./component/MediaArchiveStates";
import { MediaDetailDialog } from "./component/MediaDetailDialog";
import { MediaToolbar, type ImageQueryPreview } from "./component/MediaToolbar";
import { MediaUploadDialog } from "./component/MediaUploadDialog";
import {
  MAX_MEDIA_BYTES,
  isSupportedMediaFile,
  mediaDisplayTitle,
} from "./component/media-utils";

const PAGE_SIZE = 12;
const SEARCH_LIMIT = 30;

interface ImageQueryState {
  readonly file: File;
  readonly previewUrl: string;
}

/**
 * The standalone visual archive. `q` drives text-to-image search in the URL so
 * browser history works; image-to-image state and the open specimen stay local.
 * Results from the media endpoints never enter the text chunk index.
 */
export function MediaPage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const queryClient = useQueryClient();
  const toast = useToast();

  const submittedQuery = (searchParams.get("q") ?? "").trim();
  const [offset, setOffset] = useState(0);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [selectedMedia, setSelectedMedia] = useState<MediaSchema | null>(null);
  const [imageQueryState, setImageQueryState] = useState<ImageQueryState | null>(null);
  const [imageValidationError, setImageValidationError] = useState<string | null>(null);
  const [toolbarRevision, setToolbarRevision] = useState(0);
  const previewUrlRef = useRef<string | null>(null);

  const listQuery = useListMedia(
    { limit: PAGE_SIZE, offset },
    { query: { enabled: submittedQuery.length === 0 && imageQueryState === null } },
  );
  const textQuery = useSearchMedia(
    { query: submittedQuery, limit: SEARCH_LIMIT },
    { query: { enabled: submittedQuery.length > 0 } },
  );
  const imageSearch = useSearchMediaByImage();
  const { mutate: searchByImage, reset: resetImageSearch } = imageSearch;

  useEffect(
    () => () => {
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
        previewUrlRef.current = null;
      }
    },
    [],
  );

  const clearImageSearch = useCallback(() => {
    if (previewUrlRef.current) {
      URL.revokeObjectURL(previewUrlRef.current);
      previewUrlRef.current = null;
    }
    setImageQueryState(null);
    setImageValidationError(null);
    resetImageSearch();
  }, [resetImageSearch]);

  const removeQueryParam = useCallback(
    (options?: { readonly replace?: boolean }) => {
      if (!searchParams.has("q")) {
        return;
      }
      setSearchParams(
        (current) => {
          const next = new URLSearchParams(current);
          next.delete("q");
          return next;
        },
        { replace: options?.replace ?? false },
      );
    },
    [searchParams, setSearchParams],
  );

  const submitTextSearch = useCallback(
    (value: string) => {
      const trimmed = value.trim().slice(0, 200);
      clearImageSearch();
      setSelectedMedia(null);
      setOffset(0);
      setSearchParams((current) => {
        if ((current.get("q") ?? "") === trimmed) {
          return current;
        }
        const next = new URLSearchParams(current);
        if (trimmed.length > 0) {
          next.set("q", trimmed);
        } else {
          next.delete("q");
        }
        return next;
      });
    },
    [clearImageSearch, setSearchParams],
  );

  const clearTextSearch = useCallback(() => {
    // A restored URL query can coexist with a warm image query after history
    // navigation. Clearing text mode should also clear that stale image mode.
    if (submittedQuery.length > 0) {
      clearImageSearch();
    }
    setOffset(0);
    removeQueryParam();
  }, [clearImageSearch, removeQueryParam, submittedQuery]);

  const handleImageFile = useCallback(
    (file: File) => {
      if (!isSupportedMediaFile(file)) {
        setImageValidationError("Choose a JPEG, PNG, or WebP image for visual similarity.");
        return;
      }
      if (file.size > MAX_MEDIA_BYTES) {
        setImageValidationError("This query image is larger than the 10 MB limit.");
        return;
      }
      if (previewUrlRef.current) {
        URL.revokeObjectURL(previewUrlRef.current);
      }
      const previewUrl = URL.createObjectURL(file);
      previewUrlRef.current = previewUrl;
      setImageValidationError(null);
      setImageQueryState({ file, previewUrl });
      setSelectedMedia(null);
      setOffset(0);
      setToolbarRevision((current) => current + 1);
      removeQueryParam();
      resetImageSearch();
      searchByImage({ data: { file }, params: { limit: SEARCH_LIMIT } });
    },
    [removeQueryParam, resetImageSearch, searchByImage],
  );

  const handleUploaded = useCallback(
    (media: MediaSchema) => {
      setUploadOpen(false);
      setSelectedMedia(media);
      setOffset(0);
      clearImageSearch();
      setToolbarRevision((current) => current + 1);
      removeQueryParam({ replace: true });
      toast.success(`“${mediaDisplayTitle(media)}” joined the visual archive.`);
      void queryClient.invalidateQueries();
    },
    [clearImageSearch, queryClient, removeQueryParam, toast],
  );

  const handleUpdated = useCallback((updated: MediaSchema) => {
    setSelectedMedia((current) =>
      current && current.media_id === updated.media_id ? updated : current,
    );
  }, []);

  const handleDeleted = useCallback(() => {
    setSelectedMedia(null);
    setOffset(0);
    clearImageSearch();
  }, [clearImageSearch]);

  const handleSelectMedia = useCallback((media: MediaSchema) => {
    setSelectedMedia(media);
  }, []);

  const textMode = submittedQuery.length > 0;
  const visualMode = !textMode && imageQueryState !== null;
  let mode: MediaArchiveMode = "archive";
  if (textMode) {
    mode = "text";
  } else if (visualMode) {
    mode = "visual";
  }

  const imageQuery: ImageQueryPreview | null =
    imageQueryState && !textMode
      ? { name: imageQueryState.file.name, previewUrl: imageQueryState.previewUrl }
      : null;
  const imageLoading =
    imageSearch.isPending ||
    (visualMode && imageSearch.data === undefined && imageSearch.error === null);

  return (
    <div className="page media-page">
      <PageHeader
        eyebrow="Media · visual archive"
        title="See the archive."
        description="Images become searchable text. A vision model writes captions and reads OCR; text search looks across captions, tags, and OCR, while image search compares visual fingerprints. This visual index is standalone: it never mixes with the text library's chunks."
        meta={<span>vision captions + OCR · visual similarity · separate from text chunks</span>}
        actions={
          <div className="media-actions">
            <Badge tone="moss" dot>
              Standalone index
            </Badge>
            <Badge tone="ochre">Captions + OCR</Badge>
            <Button variant="primary" size="sm" onClick={() => setUploadOpen(true)}>
              <Icon name="plus" size={15} />
              Add image
            </Button>
          </div>
        }
      />

      <MediaToolbar
        activeQuery={submittedQuery}
        resetToken={toolbarRevision}
        onSearch={submitTextSearch}
        onClearSearch={clearTextSearch}
        onSearchByImage={handleImageFile}
        onClearImageSearch={clearImageSearch}
        imageQuery={imageQuery}
        imageSearching={imageSearch.isPending}
        imageSearchError={imageValidationError}
        onAddImage={() => setUploadOpen(true)}
      />

      <MediaArchiveStates
        mode={mode}
        query={submittedQuery}
        offset={offset}
        pageSize={PAGE_SIZE}
        textResults={textQuery.data}
        textLoading={textQuery.isLoading}
        textError={textQuery.error}
        imageResults={imageSearch.data}
        imageLoading={imageLoading}
        imageError={imageSearch.error}
        listing={listQuery.data}
        listingLoading={listQuery.isLoading}
        listingError={listQuery.error}
        onClearText={clearTextSearch}
        onClearImage={clearImageSearch}
        onAddImage={() => setUploadOpen(true)}
        onSelect={handleSelectMedia}
        onOffsetChange={setOffset}
      />

      {uploadOpen ? (
        <MediaUploadDialog onClose={() => setUploadOpen(false)} onUploaded={handleUploaded} />
      ) : null}

      {selectedMedia ? (
        <MediaDetailDialog
          key={selectedMedia.media_id}
          media={selectedMedia}
          onClose={() => setSelectedMedia(null)}
          onUpdated={handleUpdated}
          onDeleted={handleDeleted}
        />
      ) : null}
    </div>
  );
}
