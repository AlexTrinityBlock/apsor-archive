import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { useAuth } from "../../auth/AuthProvider";
import { Badge } from "../../component/Badge";
import { Button, ButtonLink } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import {
  useGetHealth,
  useGetStats,
  useSeedDemo,
} from "../../generated-apis-types";
import { formatNumber } from "../../../lib/format";
import { apiErrorMessage } from "./settings-utils";
import { SettingsDialog } from "./SettingsDialog";

/** Seed controls, access notes, version, and colophon. */
export function MaintenancePanel() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { user } = useAuth();
  const healthQuery = useGetHealth({ query: { staleTime: 30_000 } });
  const statsQuery = useGetStats({ query: { staleTime: 30_000 } });
  const [dialogOpen, setDialogOpen] = useState(false);
  const [seedError, setSeedError] = useState<string | null>(null);

  const seedDemo = useSeedDemo({
    mutation: {
      onSuccess: async (result) => {
        setSeedError(null);
        setDialogOpen(false);
        const summaryWord =
          result.summaries_created === 1 ? "summary" : "summaries";
        toast.success(
          `Seeded ${formatNumber(result.files_created)} files, ${formatNumber(result.memories_created)} memories, and ${formatNumber(result.summaries_created)} ${summaryWord}.`,
        );
        // Seeding touches every surface; this is the one allowed blanket refresh.
        await queryClient.invalidateQueries();
      },
      onError: (error) => {
        const message = apiErrorMessage(error);
        setSeedError(message);
        toast.error(message);
      },
    },
  });

  const stats = statsQuery.data;
  const archiveHasData =
    stats !== undefined && stats.file_count + stats.memory_count > 0;
  const countsUnknown = stats === undefined;
  const version = healthQuery.data?.version;
  let versionLabel = "Reading version";
  if (healthQuery.isError) {
    versionLabel = "Version unavailable";
  } else if (version) {
    versionLabel = `v${version}`;
  }

  let seedDetail =
    "Adds four sample documents, a small set of baseline memories, and one summary. Existing data is never overwritten.";
  if (archiveHasData && stats) {
    seedDetail = `The archive already holds ${formatNumber(stats.file_count)} files and ${formatNumber(stats.memory_count)} memories. The seed endpoint only accepts an empty archive.`;
  } else if (statsQuery.isPending) {
    seedDetail = "Checking the archive before seeding.";
  } else if (statsQuery.isError) {
    seedDetail =
      "The archive counts could not be read. The API will refuse to seed a non-empty archive.";
  }

  const requestSeed = () => {
    setSeedError(null);
    if (archiveHasData || countsUnknown) {
      setDialogOpen(true);
      return;
    }
    seedDemo.mutate();
  };

  const dialogDescription =
    stats !== undefined && archiveHasData
      ? `This archive already holds ${formatNumber(stats.file_count)} files and ${formatNumber(stats.memory_count)} memories.`
      : "The current archive counts could not be read.";

  return (
    <>
      <Panel
          title={
          <span className="settings-panel__title">
            <Icon name="archive" size={16} />
            Maintenance & colophon
          </span>
        }
        action={
          <Badge tone="neutral">{versionLabel}</Badge>
        }
        className="settings-panel"
      >
        <div className="maintenance-grid">
          <section className="maintenance-block">
            <p className="mono-label">Demo archive</p>
            <h3 className="maintenance-block__title">Seed the sample corpus</h3>
            <p className="maintenance-block__copy">{seedDetail}</p>
            <div className="maintenance-actions">
              <Button
                type="button"
                variant="ink"
                size="sm"
                onClick={requestSeed}
                disabled={seedDemo.isPending || statsQuery.isPending}
              >
                <Icon name="leaf" size={14} />
                {seedDemo.isPending ? "Seeding…" : "Seed demo archive"}
              </Button>
              <code className="code-inline">POST /api/v1/demo/seed</code>
            </div>
            {seedError && !dialogOpen ? (
              <p className="vault-feedback vault-feedback--error" role="alert">
                <Icon name="info" size={14} />
                {seedError}
              </p>
            ) : null}
          </section>

          <section className="maintenance-block">
            <p className="mono-label">Access</p>
            <h3 className="maintenance-block__title">Single owner account</h3>
            <p className="maintenance-block__copy">
              This archive is protected by one keeper account and a server-side
              session cookie. You are signed in as{" "}
              <strong>{user?.username ?? "the keeper"}</strong>. There is no
              cloud account, password recovery, or per-user permission model.
              Sign out from the rail when you leave a shared machine.
            </p>
          </section>
        </div>

        <div className="maintenance-colophon">
          <span>
            Apsor Archive <code>{versionLabel}</code>
          </span>
          <span>React 19 + Vite · PostgreSQL · local-first</span>
          <ButtonLink to="/method" variant="ghost" size="sm">
            Read the method
            <Icon name="arrow-right" size={14} />
          </ButtonLink>
        </div>
      </Panel>

      {dialogOpen ? (
        <SettingsDialog
          eyebrow="Maintenance · demo seed"
          title="Seed the demo archive?"
          description={dialogDescription}
          onClose={() => {
            if (!seedDemo.isPending) {
              setDialogOpen(false);
            }
          }}
          actions={
            <>
              <Button
                type="button"
                variant="ghost"
                size="sm"
                onClick={() => setDialogOpen(false)}
                disabled={seedDemo.isPending}
                data-autofocus
              >
                Cancel
              </Button>
              <Button
                type="button"
                variant="ink"
                size="sm"
                onClick={() => seedDemo.mutate()}
                disabled={seedDemo.isPending}
              >
                <Icon name="leaf" size={14} />
                {seedDemo.isPending ? "Seeding…" : "Request seed"}
              </Button>
            </>
          }
        >
          <p className="settings-dialog__copy">
            The seed endpoint only fills an empty archive. It will refuse this
            request if any files or memories already exist; nothing is deleted
            or overwritten either way.
          </p>
          {seedError ? (
            <p className="vault-feedback vault-feedback--error" role="alert">
              <Icon name="info" size={14} />
              {seedError}
            </p>
          ) : null}
        </SettingsDialog>
      ) : null}
    </>
  );
}
