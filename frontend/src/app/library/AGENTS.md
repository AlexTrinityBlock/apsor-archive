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
- **URL state:** `tab`, `path`, `q`, `view`, `file`, `chunk`, `mode`, and `media` are query parameters. `page.tsx` derives browse and preview state from them so refresh and back/forward work. Root path and defaults are omitted from the URL.
- **Views:** board is the desktop default; list is the default below 761 px and the explicit compact fallback. Sorting is client-side (`modified`, `name`, `size`, `type`) because the API exposes no sort parameter. Folders always sort by name.
- **Drag and drop:** folder cards are drop targets. Internal file drags default to move and Alt/Option-drag copies; desktop file drops upload into the target folder. The custom MIME type identifies internal drags. Touch and keyboard users use menus and dialogs instead.
- **Uploads:** drag/drop, clipboard paste, Media upload, and the intake dialog share `useLibraryUploads`. The browser enforces the extension allowlist, the 10 MB file ceiling, and the 2 MB text ceiling before enqueueing. Async upload endpoints return an `IngestJobSchema`; `waitForIngestJob` polls once per second until `ready` or `failed`. This is polling, not SSE. Closing a dialog or leaving the page cancels local polling, not the durable job.
- **Versions:** file edits and copies produce new records, not in-place overwrites. The preview shows `version`, `is_current`, `supersedes_file_id`, and soft-deletion state. Markdown saves send `expected_version`; `file_version_conflict` asks the user to reload. A successful save keeps the editor open on the new version and swaps the URL to the new file id, so typing can continue without returning to the preview.
- **Rename vs move:** rename uses the dedicated filename-only endpoint. The parent folder and extension are fixed, and the file id, version, chunks, and storage stay unchanged. Move remains the only operation that changes the folder path. Do not implement rename by exposing the full path.
- **Folder CRUD:** folders are addressed by path, not id. `renameFolder` changes only the leaf name; `moveFolder` takes a complete destination path; `copyFolder` clones the whole subtree, files, stored originals, chunks, embeddings, and ngrams without re-embedding (bounded by the backend and surfaced as `folder_copy_too_large`). Rename and move use the same subtree rewrite, so every descendant path and current file path changes. Delete reuses `deleteLibrarySelection` with `folder_paths`, which recursively soft-deletes current files while keeping history and original bytes. Every folder mutation invalidates paths, stats, timeline, and search; delete also invalidates the deleted file ids.
- **Folder action surfaces:** a folder card exposes a top-right settings trigger with the shared card-menu keyboard behaviour, and the same action order appears in the right-click context menu. The list view puts rename, move, copy, and delete icon buttons in every folder row, so touch users never depend on right-click. After a rename or move, a URL inside the old subtree is remapped to the new path while the preview file id is preserved; after a delete, a URL inside the deleted subtree falls back to its parent and a deleted preview closes. Copy leaves the browser in the current folder.
- **Selection checkbox:** selection mode is the only state that renders checkboxes. They sit at the top-left of both card types, and the folder card reserves matching padding so the box never overlaps the folder icon. The list keeps the select column first and makes it sticky while the table scrolls horizontally on mobile.
- **New notes:** the Markdown editor freezes the current folder as a read-only prefix; only the file name is editable. The create request joins that prefix with the validated name and never lets the user rewrite the folder.
- **Move vs copy:** move preserves the file id, so open citations and previews remain valid; copy creates a new file id and rebuilt chunks. Do not optimistically move a card on a `409` or `422`.
- **Batch move:** `BatchMoveDialog` sends one generated `moveFile` call at a time. It reports each failure, keeps successful moves, and leaves failed files selected for retry.
- **Markdown editor:** loads the original text when available, otherwise reconstructs from indexed chunks. It lazy-loads the preview, tracks dirty state, guards close/beforeunload, supports Cmd/Ctrl+S, and reports new-file name conflicts separately. A save does not close the editor: an existing file stays in edit mode on its new version, and a newly created note transitions the dialog to edit mode for continued typing. In the preview modal, edit mode hides the preview masthead/tabs so the Markdown editor header is the only header.
- **Context menu:** `ContextMenu` is shared and portaled above the Library modal. Right-click, the ContextMenu key, and Shift+F10 open the same actions. Mobile cards expose actions directly, so drag is never the only path.
- **Media:** the Media tab filters images from the same listing locally and opens the same `FilePreviewModal`; it has no separate file API.

## Key files

- `page.tsx` — URL state, listing, selection, dialogs, mutations, and query invalidation.
- `component/library-utils.ts` — path rules, upload limits, sorting, filtering, polling, and invalidation helpers.
- `component/LibraryToolbar.tsx`, `LibraryBreadcrumbs.tsx` — search, sort, tabs, view controls, and path navigation.
- `component/LibraryFilesContent.tsx`, `LibraryBoard.tsx`, `LibraryResults.tsx` — board/list rendering, drop targets, card menus, and empty states.
- `component/LibraryMediaGallery.tsx` — image gallery and local filter.
- `component/LibraryDialog.tsx` — shared modal with focus trap, scroll lock, Escape, and focus return.
- `component/UploadDialog.tsx`, `IngestProgress.tsx`, `LibraryUploadTray.tsx` — intake tabs, durable-job progress, retry, and tray.
- `hook/useLibraryUploads.ts` — shared upload queue and abort handling.
- `hook/useIngestRun.ts` — dialog-scoped enqueue/poll lifecycle.
- `component/MoveCopyDialog.tsx`, `BatchMoveDialog.tsx`, `NewFolderDialog.tsx`, `DeleteFileDialog.tsx` — file operations and confirmations.
- `component/RenameFolderDialog.tsx`, `MoveCopyFolderDialog.tsx`, `DeleteFolderDialog.tsx` — folder rename, move/copy, and recursive delete confirmations.
- `component/FilePreviewModal.tsx` — preview tabs, version state, download, rename, move/copy/delete, and edit.
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
