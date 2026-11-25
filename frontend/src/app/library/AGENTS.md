# frontend/src/app/library/ — Agent Guide

The `/library` file workspace: folder-first browsing, media, uploads, preview, Markdown editing, move/copy/delete, and batch selection. It owns archive navigation and file actions, while reusing the shared viewer and generated API hooks.

## Purpose

- Browse one path listing as a folder-first board or compact list.
- Open files in an in-situ preview with chunk inspection and version metadata.
- Ingest files and plain text through durable jobs with visible progress.
- Edit current Markdown files safely against their version.
- Perform move, copy, soft delete, folder creation, folder rename/move/copy, and batch move without breaking citations or open previews.

Backend validation remains authoritative. The UI mirrors limits for fast feedback, normalizes paths, and surfaces stable API errors.

## Architecture

- **One listing:** `useReadPath({ path, path_depth: 1, fuzzy_search })` feeds the Files tab, Media tab, counts, and search. Board and list are two presentations of the same payload; switching views does not refetch a different contract.
- **URL state:** resources use REST path parameters: `/library/folders/<encoded path>`, `/library/files/:id`, and the `/library/media` variants. `q`, `view`, `chunk`, and `mode` remain query parameters because they refine the current resource. Root collection URLs omit the folder suffix. `page.tsx` derives browse and preview state from the pathname so refresh and back/forward work. Legacy `/library?path=...&file=...` links redirect to the canonical form.
- **Folder encoding:** folder names are user text. Encode every archive segment with `encodeURIComponent` and decode exactly once when parsing; reject empty, traversal, separator, and control segments instead of throwing. Never interpolate a raw archive path into a route or query string. File resources use numeric ids, so file names never enter the URL.
- **Views:** board is the default at every width; `?view=list` selects the compact table fallback. Sorting is client-side (`modified`, `name`, `size`, `type`) because the API exposes no sort parameter. Folders always sort by name.
- **Thumbnail loading:** supported thumbnails center a quiet spinner over the paper while a preview is queued or rendering; off-screen cards stay static, and failures fall back to the type tile.
- **Drag and drop:** folder cards are drop targets. Internal file drags default to move and Alt/Option-drag copies; desktop file drops upload into the target folder. The custom MIME type identifies internal drags. Touch and keyboard users use menus and dialogs instead.
- **Uploads:** drag/drop, clipboard paste, and the intake dialog share `useLibraryUploads`; the Media picker uses the same queue but keeps its own image-only allowlist (`IMAGE_UPLOAD_ACCEPT`). The intake dialog has no archive-path field: uploads target the open folder or the folder action that opened the dialog, and the picker accepts several files at once. A clipboard paste whose name is already occupied in the target folder gets the first free ` (n)` suffix, including collisions inside one paste; drag/drop and the intake dialog keep the explicit same-name version behavior. Folder paths are never typed; a new branch is created through the name-only New folder dialog and the `createFolder` API. The file intake enforces the extension allowlist (`.md`, `.markdown`, `.txt`, `.csv`, `.json`, `.log`, `.pdf`, `.docx`, `.pptx`, `.xlsx`, `.xls`, `.xlsm`, `.ods`, `.jpg`, `.jpeg`, `.png`, `.webp`), the 10 MB per-file ceiling, and the 2 MB text ceiling before enqueueing. Spreadsheets are extracted as text and previewed as a bounded sheet grid; they are not images and never enter the Media tab. Async upload endpoints return an `IngestJobSchema`; the page watches the job over a fetch-based SSE progress stream and merges each compact `snapshot`/`progress` event into the enqueue job. A stream error or early close falls back to the existing one-second `waitForIngestJob` polling helper, so a lost Pub/Sub message only costs a UI update. Closing a dialog or leaving the page cancels local streaming/polling, not the durable job.
- **Versions:** file edits and copies produce new records, not in-place overwrites. The preview shows `version`, `is_current`, `supersedes_file_id`, and soft-deletion state. Markdown saves send `expected_version`; `file_version_conflict` asks the user to reload. A successful save keeps the editor open on the new version and swaps the URL to the new file id, so typing can continue without returning to the preview.
- **Extraction trace:** the Metadata tab appends an Extraction section that reports `extraction_method`, the recorded vision prompt mode and description language, and the short `vision_prompt_sha256` with the full hash and copy control inside `<details>`. A null fingerprint is shown as the legacy state for vision-capable files; text-based files say no vision prompt applies. The Re-ingest action is disabled for historical/deleted rows, files without a stored original, non-image/PDF/DOCX/PPTX types, and an active run, with a visible reason.
- **Re-ingest:** `useFileReingest` lives at Library page level so closing the preview does not stop watching the job. The hook enqueues through the generated `reingestFile` hook with `expected_version`, watches progress over SSE with `waitForIngestJob` as the polling fallback, guards async work with a generation counter and `AbortController`, and exposes confirmation, already-processing, processing, failure, and success state to `ReingestDialog`. Re-ingest creates a new file version and never mutates the current row; the old version remains current until publish succeeds. A `409 ingest_job_conflict` is shown as an already-processing note, not a red failure. Success invalidates paths, stats, timeline, search, and both file ids, and navigates to the new id when the preview is still on the source. Prompt saves never trigger re-ingest automatically. Spreadsheet rows are excluded because re-ingest is vision-only; a spreadsheet must be re-uploaded to apply a future extraction change.
- **PDF on mobile:** the preview header collapses to one thin file-name/tab row and hides the metadata/action bar; document details live in the Meta tab and file actions remain in the library layer. The PDF toolbar is sticky, the modal body owns vertical scrolling, and the PDF area owns horizontal panning only, so zoom controls and page dragging coexist. The zoom percentage is also the reset-to-100% control, which keeps the toolbar on one row at 390px. The page frame shrinks to the rendered canvas so narrow pages center instead of hugging the left edge, and the fit-width observer attaches through a callback ref because the scroll surface mounts only after the binary loads.
- **PDF fullscreen:** the toolbar's fullscreen toggle promotes the viewer to a fixed, full-viewport surface that owns both scroll axes; on supported desktop and Android browsers it also requests native fullscreen, while iOS Safari keeps the in-app overlay. Escape exits fullscreen before closing the preview, and Tab stays inside the viewer.
- **Rename vs move:** rename uses the dedicated filename-only endpoint. The parent folder and extension are fixed, and the file id, version, chunks, and storage stay unchanged. Move remains the only operation that changes the folder path. Do not implement rename by exposing the full path.
- **Folder CRUD:** folders are addressed by path, not id. Creation is name-only inside the current folder and always calls `createFolder`; the dialog never accepts a free-form archive path. `renameFolder` changes only the leaf name; `moveFolder` takes a complete destination path; `copyFolder` clones the whole subtree, files, stored originals, chunks, embeddings, and ngrams without re-embedding (bounded by the backend and surfaced as `folder_copy_too_large`). Rename and move use the same subtree rewrite, so every descendant path and current file path changes. Delete reuses `deleteLibrarySelection` with `folder_paths`, which recursively soft-deletes current files while keeping history and original bytes. Every folder mutation invalidates paths, stats, timeline, and search; delete also invalidates the deleted file ids.
- **Folder action surfaces:** a folder card exposes a top-right settings trigger with the shared card-menu keyboard behaviour, and the same action order appears in the right-click context menu. The list view puts rename, move, copy, and delete icon buttons in every folder row, so touch users never depend on right-click. After a rename or move, a URL inside the old subtree is remapped to the new path while the preview file id is preserved; after a delete, a URL inside the deleted subtree falls back to its parent and a deleted preview closes. Copy leaves the browser in the current folder.
- **Selection checkbox:** selection mode is the only state that renders checkboxes. They sit at the top-left of both card types, and the folder card reserves matching padding so the box never overlaps the folder icon. The list keeps the select column first and makes it sticky while the table scrolls horizontally on mobile.
- **New notes:** the Markdown editor freezes the current folder as a read-only prefix; only the file name is editable. The create request joins that prefix with the validated name and never lets the user rewrite the folder.
- **Move vs copy:** move preserves the file id, so open citations and previews remain valid; copy creates a new file id and rebuilt chunks. Do not optimistically move a card on a `409` or `422`.
- **Batch move:** `BatchMoveDialog` sends one generated `moveFile` call at a time. It reports each failure, keeps successful moves, and leaves failed files selected for retry.
- **Markdown editor:** loads the original text when available, otherwise reconstructs from indexed chunks. It lazy-loads the preview, tracks dirty state, guards close/beforeunload, supports Cmd/Ctrl+S, and reports new-file name conflicts separately. A save does not close the editor: an existing file stays in edit mode on its new version, and a newly created note transitions the dialog to edit mode for continued typing. In the preview modal, edit mode hides the preview masthead/tabs so the Markdown editor header is the only header. On mobile the full-screen editor and preview shell consume the app-level visual viewport variables (`AppShell` owns the listener), so the on-screen keyboard cannot cover the textarea or the save footer; a focused textarea re-scrolls its caret after the viewport shrinks, and the mobile textarea uses 16px text to prevent iOS focus zoom.
- **Context menu:** `ContextMenu` is shared and portaled above the Library modal. Right-click, the ContextMenu key, and Shift+F10 open the same actions. Mobile cards expose actions directly, so drag is never the only path.
- **Media:** the Media tab filters images from the same listing locally and opens the same `FilePreviewModal`; it has no separate file API.

## Key files

- `page.tsx` — URL state, listing, selection, dialogs, mutations, and query invalidation.
- `../../lib/library-url.ts` — canonical folder/file URL builders, segment encoding and decoding, and legacy redirects.
- `component/library-utils.ts` — path rules, upload limits, sorting, filtering, the SSE-aware job watcher, polling fallback, and invalidation helpers.
- `component/ingest-progress.ts` — pure progress resolution shared by the meter and its tests.
- `../../apis/ingest-stream.ts` — fetch-based SSE transport and compact-event merge for durable ingestion progress.
- `component/LibraryToolbar.tsx`, `LibraryBreadcrumbs.tsx` — search, sort, tabs, view controls, and path navigation.
- `component/LibraryFilesContent.tsx`, `LibraryBoard.tsx`, `LibraryResults.tsx` — board/list rendering, drop targets, card menus, and empty states.
- `component/LibraryMediaGallery.tsx` — image gallery and local filter.
- `component/LibraryDialog.tsx` — shared modal with focus trap, scroll lock, Escape, and focus return.
- `component/UploadDialog.tsx`, `IngestProgress.tsx`, `LibraryUploadTray.tsx` — intake tabs, durable-job progress, retry, and tray.
- `hook/useLibraryUploads.ts` — shared upload queue and abort handling.
- `hook/useIngestRun.ts` — dialog-scoped enqueue/poll lifecycle.
- `component/MoveCopyDialog.tsx`, `BatchMoveDialog.tsx`, `NewFolderDialog.tsx`, `DeleteFileDialog.tsx` — file operations and confirmations.
- `component/RenameFolderDialog.tsx`, `MoveCopyFolderDialog.tsx`, `DeleteFolderDialog.tsx` — folder rename, move/copy, and recursive delete confirmations.
- `component/FilePreviewModal.tsx` — preview tabs, version state, download, rename, move/copy/delete, extraction trace, and edit.
- `component/ExtractionTracePanel.tsx` — Metadata extraction method, prompt mode/language, fingerprint details, legacy state, and eligible re-ingest action.
- `component/ReingestDialog.tsx` — LibraryDialog shell for confirmation, durable-job progress, failure, already-processing, and success.
- `hook/useFileReingest.ts` — page-level re-ingest enqueue/poll lifecycle with abort and generation guards.
- `component/RenameFileDialog.tsx` — fixed folder + fixed extension, editable stem only.
- `component/MarkdownEditor.tsx`, `MarkdownEditorDialog.tsx`, `MarkdownToolbar.tsx`, `markdown-edit.ts`, `useMarkdownDocument.ts` — editor, formatting, fixed-folder new-note form, content loading, and dirty guards.
- `component/LibrarySelectionBar.tsx` — selection count, select-all, clear, and batch move entry.
- `library.css` — page composition and responsive rules; shared primitives remain in `src/styles/` and `app/component/`.

## Conventions

- Use generated `useReadPath`, `useUploadFileAsync`, `useCreateTextFileAsync`, `useRetryIngestJob`, `useGetFile`, `useReadFile`, `useUpdateFileContent`, `useRenameFile`, `moveFile`, `copyFile`, `renameFolder`, `moveFolder`, `copyFolder`, and `useDeleteFile`. Do not add a Library-specific fetch client.
- Rename is filename-only. Never send a full path to the rename endpoint or expose the parent folder as an input. Move/copy remain the path-changing operations.
- Reuse `../viewer/component/viewer-utils.ts` and `FileRenderer` for content and previews. Do not create a second renderer or download path.
- After any mutation, call `invalidateLibraryQueries` with only the affected surfaces and file ids. Update the current preview path when a move changes its folder.
- Normalize every archive path to an absolute path; reject empty, traversal-like, or separator-containing upload names before upload. The server repeats validation.
- Keep version semantics explicit: never update content without `expected_version`, never silently retry a version conflict, and never reuse a moved file's id for a copy.
- Keep re-ingest limited to current, non-deleted images, PDF, DOCX, and PPTX rows with `has_original`. It always creates a new version through the generated `reingestFile` hook and never mutates the source row or its chunks. Do not auto-re-ingest on prompt save, do not allow text/Markdown/CSV/JSON/spreadsheet rows, and do not delete shared original bytes when a job fails or is dismissed.
- Preserve URL state. Opening a preview, chunk, edit mode, folder, or media item should be linkable and survive refresh.
- Keep workspace copy in the `library` namespace across all three locales; shared error and status copy remains under `core`.
- Use `min-width: 0`, wrapping, and the existing 900/760/720/560 breakpoints. The workspace must not overflow horizontally at 390 px, and every action must remain reachable without drag.
- Respect reduced-motion preferences and the shared focus treatment.

## Verification

```bash
cd frontend
bun run lint
bun run typecheck
bun run i18n:check
bun run build
```

Manually verify board/list switching, deep-linked previews, upload progress, move/copy conflicts, version-conflict editing, and the mobile action path.

## Related guides

- [Application layer](../AGENTS.md)
- [Settings](../settings/AGENTS.md)
- [Internationalization](../i18n/AGENTS.md)
- [Global styles](../../styles/AGENTS.md)
