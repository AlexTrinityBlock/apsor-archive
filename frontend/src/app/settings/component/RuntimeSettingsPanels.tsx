import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";

import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Panel } from "../../component/Panel";
import { useToast } from "../../component/Toast";
import {
  getGetAgentSettingsQueryKey,
  getGetIngestSettingsQueryKey,
  useGetAgentSettings,
  useGetIngestSettings,
  useResetAgentSettings,
  useResetIngestSettings,
  useUpdateAgentSettings,
  useUpdateIngestSettings,
} from "../../generated-apis-types";
import { AgentRuntimePanel } from "./AgentRuntimePanel";
import { IngestRuntimePanel } from "./IngestRuntimePanel";
import { apiErrorMessage } from "./settings-utils";

/** Loads, saves, and resets the database-backed agent runtime limits. */
export function AgentRuntimeSettingsPanel() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [panelRevision, setPanelRevision] = useState(0);

  const settingsQuery = useGetAgentSettings({ query: { staleTime: 60_000 } });

  const refreshSettings = async (): Promise<void> => {
    await queryClient.invalidateQueries({
      queryKey: getGetAgentSettingsQueryKey(),
      refetchType: "active",
    });
  };

  const updateSettings = useUpdateAgentSettings({
    mutation: {
      onSuccess: async (settings) => {
        queryClient.setQueryData(getGetAgentSettingsQueryKey(), settings);
        setMutationError(null);
        toast.success("Agent runtime settings saved to the database.");
        await refreshSettings();
      },
      onError: (error) => {
        setMutationError(apiErrorMessage(error));
      },
    },
  });

  const resetSettings = useResetAgentSettings({
    mutation: {
      onSuccess: async (settings) => {
        queryClient.setQueryData(getGetAgentSettingsQueryKey(), settings);
        setMutationError(null);
        setPanelRevision((current) => current + 1);
        toast.success("Agent runtime settings reset to defaults.");
        await refreshSettings();
      },
      onError: (error) => {
        setMutationError(apiErrorMessage(error));
      },
    },
  });

  const settings = settingsQuery.data;

  if (settingsQuery.isPending) {
    return (
      <Panel
        title={
          <span className="settings-panel__title">
            <Icon name="spark" size={16} />
            Agent runtime
          </span>
        }
        className="settings-panel runtime-panel"
      >
        <div
          className="runtime-loading"
          role="status"
          aria-busy="true"
          aria-label="Reading agent runtime settings"
        >
          <span className="settings-skeleton settings-skeleton--line" />
          <span className="settings-skeleton settings-skeleton--line is-short" />
          <span className="settings-skeleton settings-skeleton--field" />
          <span className="settings-skeleton settings-skeleton--field" />
        </div>
      </Panel>
    );
  }

  if (settingsQuery.isError || !settings) {
    return (
      <Panel
        title={
          <span className="settings-panel__title">
            <Icon name="spark" size={16} />
            Agent runtime
          </span>
        }
        className="settings-panel runtime-panel"
      >
        <div className="settings-inline-error" role="alert">
          <Icon name="info" size={16} />
          <div>
            <strong>Agent runtime settings did not answer.</strong>
            <p>{apiErrorMessage(settingsQuery.error)}</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void settingsQuery.refetch()}
              disabled={settingsQuery.isFetching}
            >
              <Icon name="ring" size={14} />
              {settingsQuery.isFetching ? "Retrying…" : "Retry"}
            </Button>
          </div>
        </div>
      </Panel>
    );
  }

  const saving = updateSettings.isPending || resetSettings.isPending;

  return (
    <AgentRuntimePanel
      key={panelRevision}
      values={settings.config}
      defaults={settings.defaults}
      source={settings.source}
      updatedAt={settings.updated_at}
      saving={saving}
      error={mutationError}
      onSave={(values) => {
        setMutationError(null);
        updateSettings.mutate({ data: values });
      }}
      onReset={() => {
        setMutationError(null);
        resetSettings.mutate();
      }}
    />
  );
}

/** Loads, saves, and resets the database-backed ingestion worker settings. */
export function IngestRuntimeSettingsPanel() {
  const queryClient = useQueryClient();
  const toast = useToast();
  const [mutationError, setMutationError] = useState<string | null>(null);
  const [panelRevision, setPanelRevision] = useState(0);

  const settingsQuery = useGetIngestSettings({ query: { staleTime: 60_000 } });

  const refreshSettings = async (): Promise<void> => {
    await queryClient.invalidateQueries({
      queryKey: getGetIngestSettingsQueryKey(),
      refetchType: "active",
    });
  };

  const updateSettings = useUpdateIngestSettings({
    mutation: {
      onSuccess: async (settings) => {
        queryClient.setQueryData(getGetIngestSettingsQueryKey(), settings);
        setMutationError(null);
        toast.success("Ingestion runtime settings saved to the database.");
        await refreshSettings();
      },
      onError: (error) => {
        setMutationError(apiErrorMessage(error));
      },
    },
  });

  const resetSettings = useResetIngestSettings({
    mutation: {
      onSuccess: async (settings) => {
        queryClient.setQueryData(getGetIngestSettingsQueryKey(), settings);
        setMutationError(null);
        setPanelRevision((current) => current + 1);
        toast.success("Ingestion runtime settings reset to defaults.");
        await refreshSettings();
      },
      onError: (error) => {
        setMutationError(apiErrorMessage(error));
      },
    },
  });

  const settings = settingsQuery.data;

  if (settingsQuery.isPending) {
    return (
      <Panel
        title={
          <span className="settings-panel__title">
            <Icon name="layers" size={16} />
            Ingestion runtime
          </span>
        }
        className="settings-panel runtime-panel"
      >
        <div
          className="runtime-loading"
          role="status"
          aria-busy="true"
          aria-label="Reading ingestion runtime settings"
        >
          <span className="settings-skeleton settings-skeleton--line" />
          <span className="settings-skeleton settings-skeleton--line is-short" />
          <span className="settings-skeleton settings-skeleton--field" />
          <span className="settings-skeleton settings-skeleton--field" />
        </div>
      </Panel>
    );
  }

  if (settingsQuery.isError || !settings) {
    return (
      <Panel
        title={
          <span className="settings-panel__title">
            <Icon name="layers" size={16} />
            Ingestion runtime
          </span>
        }
        className="settings-panel runtime-panel"
      >
        <div className="settings-inline-error" role="alert">
          <Icon name="info" size={16} />
          <div>
            <strong>Ingestion runtime settings did not answer.</strong>
            <p>{apiErrorMessage(settingsQuery.error)}</p>
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => void settingsQuery.refetch()}
              disabled={settingsQuery.isFetching}
            >
              <Icon name="ring" size={14} />
              {settingsQuery.isFetching ? "Retrying…" : "Retry"}
            </Button>
          </div>
        </div>
      </Panel>
    );
  }

  const saving = updateSettings.isPending || resetSettings.isPending;

  return (
    <IngestRuntimePanel
      key={panelRevision}
      values={settings.config}
      defaults={settings.defaults}
      source={settings.source}
      updatedAt={settings.updated_at}
      saving={saving}
      error={mutationError}
      onSave={(values) => {
        setMutationError(null);
        updateSettings.mutate({ data: values });
      }}
      onReset={() => {
        setMutationError(null);
        resetSettings.mutate();
      }}
    />
  );
}
