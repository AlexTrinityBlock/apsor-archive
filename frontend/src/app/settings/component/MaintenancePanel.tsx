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
import { useI18n } from "../../i18n";
import { apiErrorMessage } from "./settings-utils";
import { SettingsDialog } from "./SettingsDialog";

/** Seed controls, access notes, version, and colophon. */
export function MaintenancePanel() {
  const { t, formatNumber } = useI18n();
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
        toast.success(
          t(
            result.summaries_created === 1
              ? "settings.maintenance.seededOne"
              : "settings.maintenance.seededOther",
            {
              files: formatNumber(result.files_created),
              memories: formatNumber(result.memories_created),
              summaries: formatNumber(result.summaries_created),
            },
          ),
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
  let versionLabel = t("settings.maintenance.readingVersion");
  if (healthQuery.isError) {
    versionLabel = t("settings.maintenance.versionUnavailable");
  } else if (version) {
    versionLabel = t("settings.maintenance.version", { version });
  }

  let seedDetail = t("settings.maintenance.seedDetailDefault");
  if (archiveHasData && stats) {
    seedDetail = t("settings.maintenance.seedDetailExisting", {
      files: formatNumber(stats.file_count),
      memories: formatNumber(stats.memory_count),
    });
  } else if (statsQuery.isPending) {
    seedDetail = t("settings.maintenance.seedDetailPending");
  } else if (statsQuery.isError) {
    seedDetail = t("settings.maintenance.seedDetailError");
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
      ? t("settings.maintenance.dialogDescriptionExisting", {
          files: formatNumber(stats.file_count),
          memories: formatNumber(stats.memory_count),
        })
      : t("settings.maintenance.dialogDescriptionUnknown");

  return (
    <>
      <Panel
          title={
          <span className="settings-panel__title">
            <Icon name="archive" size={16} />
            {t("settings.maintenance.title")}
          </span>
        }
        action={
          <Badge tone="neutral">{versionLabel}</Badge>
        }
        className="settings-panel"
      >
        <div className="maintenance-grid">
          <section className="maintenance-block">
            <p className="mono-label">{t("settings.maintenance.demoArchive")}</p>
            <h3 className="maintenance-block__title">
              {t("settings.maintenance.seedTitle")}
            </h3>
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
                {seedDemo.isPending
                  ? t("settings.maintenance.seeding")
                  : t("settings.maintenance.seedAction")}
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
            <p className="mono-label">{t("settings.maintenance.access")}</p>
            <h3 className="maintenance-block__title">
              {t("settings.maintenance.accessTitle")}
            </h3>
            <p className="maintenance-block__copy">
              {t("settings.maintenance.accessCopyBefore")}
              <strong>
                {user?.username ?? t("settings.maintenance.keeperFallback")}
              </strong>
              {t("settings.maintenance.accessCopyAfter")}
            </p>
          </section>
        </div>

        <div className="maintenance-colophon">
          <span>
            Apsor Archive <code>{versionLabel}</code>
          </span>
          <span>React 19 + Vite · PostgreSQL · local-first</span>
          <ButtonLink to="/method" variant="ghost" size="sm">
            {t("settings.maintenance.readMethod")}
            <Icon name="arrow-right" size={14} />
          </ButtonLink>
        </div>
      </Panel>

      {dialogOpen ? (
        <SettingsDialog
          eyebrow={t("settings.maintenance.dialogEyebrow")}
          title={t("settings.maintenance.dialogTitle")}
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
                {t("settings.common.cancel")}
              </Button>
              <Button
                type="button"
                variant="ink"
                size="sm"
                onClick={() => seedDemo.mutate()}
                disabled={seedDemo.isPending}
              >
                <Icon name="leaf" size={14} />
                {seedDemo.isPending
                  ? t("settings.maintenance.seeding")
                  : t("settings.maintenance.requestSeed")}
              </Button>
            </>
          }
        >
          <p className="settings-dialog__copy">
            {t("settings.maintenance.dialogCopy")}
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
