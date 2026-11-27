/**
 * Compatibility re-export for the memory workspace, which still imports the
 * confirmation dialog from Settings. Import `component/ConfirmDialog` instead;
 * delete this file once memory moves to the shared import.
 */
export { ConfirmDialog as SettingsDialog } from "../../component/ConfirmDialog";
