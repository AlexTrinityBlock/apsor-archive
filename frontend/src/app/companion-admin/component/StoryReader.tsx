import { useState } from "react";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useToast } from "../../component/Toast";
import {
  useCancelCompanionStoryJobAdmin,
  useDeleteCompanionGeneratedStoryAdmin,
  useGenerateCompanionStoryAdmin,
  useGetCompanionGeneratedStoryAdmin,
  useListCompanionAccessLogAdmin,
  useListCompanionGeneratedStoriesAdmin,
  useListCompanionStoryJobsAdmin,
  useRegenerateCompanionGeneratedStoryAdmin,
  useUpdateCompanionGeneratedStoryAdmin,
} from "../../generated-apis-types";
import type { CompanionGeneratedStorySchema } from "../../generated-apis-types/schemas";
import { useApiErrorMessage, useI18n } from "../../i18n";
import { useAdminRefresh } from "../hook/useAdminRefresh";

interface StoryReaderProps {
  readonly userId: number;
  readonly companionRef: string;
  readonly locale: "en" | "zh-TW" | "zh-CN";
  readonly names: ReadonlyMap<string, string>;
}

type StoryStatus = "draft" | "published" | "retired";
const STATUSES: readonly StoryStatus[] = ["draft", "published", "retired"];

/**
 * Life stories written for one account. The list shows only titles and
 * counts; opening a story fetches its text, which the server records.
 */
export function StoryReader({
  userId,
  companionRef,
  locale,
  names,
}: StoryReaderProps) {
  const { t, formatDateTime, formatNumber } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const [openId, setOpenId] = useState<number | null>(null);
  const stories = useListCompanionGeneratedStoriesAdmin(userId, {
    query: { retry: false },
  });
  const jobs = useListCompanionStoryJobsAdmin(userId, {
    query: { retry: false },
  });
  const generate = useGenerateCompanionStoryAdmin();
  const cancel = useCancelCompanionStoryJobAdmin();

  const run = async (action: () => Promise<unknown>, success: string) => {
    try {
      await action();
      refresh();
      toast.success(success);
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "companionAdmin.world.error"));
    }
  };

  const ownStories = (stories.data ?? []).filter(
    (story) => story.companion_ref === companionRef,
  );

  return (
    <div className="ca-stories">
      <div className="ca-door">
        <img
          src="/companions/world/illusory-door.avif"
          alt=""
          width={1024}
          height={683}
          loading="lazy"
          decoding="async"
          className="ca-door__art"
        />
        <div className="ca-door__copy">
          <p className="ca-banner" role="note">
            <Icon name="info" size={14} />
            {t("companionAdmin.stories.banner")}
          </p>
          <Button
            type="button"
            variant="primary"
            size="sm"
            disabled={generate.isPending}
            onClick={() =>
              void run(
                () =>
                  generate.mutateAsync({
                    userId,
                    data: { companion_ref: companionRef, locale },
                  }),
                t("companionAdmin.templates.draftQueued", {
                  name: names.get(companionRef) ?? companionRef,
                }),
              )
            }
          >
            <Icon name="spark" size={14} />
            {t("companionAdmin.stories.generate")}
          </Button>
          <p className="ca-hint">{t("companionAdmin.stories.generateHint")}</p>
        </div>
      </div>

      {stories.isPending ? (
        <Loader label={t("companionAdmin.world.loading")} />
      ) : null}
      {!stories.isPending && ownStories.length === 0 ? (
        <p className="ca-empty">{t("companionAdmin.stories.empty")}</p>
      ) : null}
      {ownStories.length > 0 ? (
        <ul className="ca-story-list">
          {ownStories.map((story) => (
            <li key={story.id} className="ca-story-row">
              <div className="ca-story-row__main">
                <strong>{story.title}</strong>
                <span className="ca-story-row__meta">
                  {formatDateTime(story.created_at)} ·{" "}
                  {t(`companionAdmin.stories.statuses.${story.status}`)} ·{" "}
                  {t("companionAdmin.stories.toldTimes", {
                    count: formatNumber(story.told_count),
                  })}
                  {story.admin_edited_at
                    ? ` · ${t("companionAdmin.stories.edited")}`
                    : ""}
                </span>
              </div>
              <Button
                type="button"
                variant={openId === story.id ? "ink" : "secondary"}
                size="sm"
                onClick={() => setOpenId(openId === story.id ? null : story.id)}
              >
                {openId === story.id
                  ? t("companionAdmin.stories.close")
                  : t("companionAdmin.stories.open")}
              </Button>
              {openId === story.id ? (
                <StoryEditor
                  userId={userId}
                  storyId={story.id}
                  onClosed={() => setOpenId(null)}
                />
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}

      <section className="ca-subsection" aria-labelledby={`jobs-${userId}`}>
        <h4 id={`jobs-${userId}`}>
          {t("companionAdmin.companion.sections.jobs")}
        </h4>
        {(jobs.data ?? []).length === 0 ? (
          <p className="ca-empty">{t("companionAdmin.jobs.empty")}</p>
        ) : (
          <ul className="ca-job-list">
            {(jobs.data ?? []).map((job) => (
              <li key={job.id} className={`ca-job ca-job--${job.status}`}>
                <span className="ca-job__status">
                  {t(`companionAdmin.jobs.statuses.${job.status}`)}
                </span>
                <span>
                  {t(`companionAdmin.jobs.triggers.${job.trigger}`)} ·{" "}
                  {names.get(job.companion_ref) ?? job.companion_ref} ·{" "}
                  {formatDateTime(job.created_at)}
                  {job.skip_reason ? ` · ${job.skip_reason}` : ""}
                  {job.error_code ? ` · ${job.error_code}` : ""}
                </span>
                {job.status === "queued" || job.status === "running" ? (
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    disabled={cancel.isPending}
                    onClick={() =>
                      void run(
                        () => cancel.mutateAsync({ userId, jobId: job.id }),
                        t("companionAdmin.world.saved"),
                      )
                    }
                  >
                    {t("companionAdmin.jobs.cancel")}
                  </Button>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
      <AccessRecord userId={userId} />
    </div>
  );
}

function StoryEditor({
  userId,
  storyId,
  onClosed,
}: {
  readonly userId: number;
  readonly storyId: number;
  readonly onClosed: () => void;
}) {
  const { t } = useI18n();
  const story = useGetCompanionGeneratedStoryAdmin(userId, storyId, {
    query: { retry: false, staleTime: Infinity },
  });
  if (story.isPending) {
    return <Loader label={t("companionAdmin.world.loading")} />;
  }
  if (story.isError || !story.data) {
    return <p className="ca-empty">{t("companionAdmin.world.loadError")}</p>;
  }
  return (
    <StoryForm
      key={story.data.id}
      userId={userId}
      story={story.data}
      onClosed={onClosed}
    />
  );
}

function StoryForm({
  userId,
  story,
  onClosed,
}: {
  readonly userId: number;
  readonly story: CompanionGeneratedStorySchema;
  readonly onClosed: () => void;
}) {
  const { t, formatNumber } = useI18n();
  const toast = useToast();
  const apiErrorMessage = useApiErrorMessage();
  const refresh = useAdminRefresh();
  const [title, setTitle] = useState(story.title);
  const [text, setText] = useState(story.text);
  const [status, setStatus] = useState<StoryStatus>(story.status);
  const update = useUpdateCompanionGeneratedStoryAdmin();
  const regenerate = useRegenerateCompanionGeneratedStoryAdmin();
  const remove = useDeleteCompanionGeneratedStoryAdmin();
  const busy = update.isPending || regenerate.isPending || remove.isPending;
  const memories = story.source_counts.memory ?? 0;
  const files = story.source_counts.file ?? 0;

  const run = async (action: () => Promise<unknown>, after?: () => void) => {
    try {
      await action();
      refresh();
      toast.success(t("companionAdmin.world.saved"));
      after?.();
    } catch (caught) {
      toast.error(apiErrorMessage(caught, "companionAdmin.world.error"));
    }
  };

  return (
    <article className="ca-story-reader">
      <p className="ca-story-reader__recorded">
        <Icon name="key" size={12} />
        {t("companionAdmin.stories.viewRecorded")}
      </p>
      <p className="ca-story-reader__meta">
        {t("companionAdmin.stories.meta", {
          chars: formatNumber(story.chars),
          model: story.model ?? "—",
        })}{" "}
        ·{" "}
        {t("companionAdmin.stories.sources", {
          memories: formatNumber(memories),
          files: formatNumber(files),
        })}
      </p>
      <label className="ca-field">
        <span>{t("companionAdmin.stories.title")}</span>
        <input
          className="input"
          value={title}
          maxLength={120}
          onChange={(event) => setTitle(event.target.value)}
        />
      </label>
      <label className="ca-field">
        <span>{t("companionAdmin.stories.text")}</span>
        <textarea
          className="input ca-story-reader__text"
          value={text}
          maxLength={4000}
          rows={12}
          onChange={(event) => setText(event.target.value)}
        />
      </label>
      <div className="ca-row">
        <label className="ca-field">
          <span>{t("companionAdmin.stories.status")}</span>
          <select
            className="input"
            value={status}
            onChange={(event) => setStatus(event.target.value as StoryStatus)}
          >
            {STATUSES.map((item) => (
              <option key={item} value={item}>
                {t(`companionAdmin.stories.statuses.${item}`)}
              </option>
            ))}
          </select>
        </label>
        <Badge tone="ochre">
          {t(`companionAdmin.fragments.tiers.${story.tier}`)}
        </Badge>
      </div>
      <div className="ca-actions">
        <Button
          type="button"
          variant="primary"
          size="sm"
          disabled={busy || !title.trim() || !text.trim()}
          onClick={() =>
            void run(() =>
              update.mutateAsync({
                userId,
                storyId: story.id,
                data: { title, text, status },
              }),
            )
          }
        >
          {t("companionAdmin.stories.save")}
        </Button>
        <Button
          type="button"
          variant="secondary"
          size="sm"
          disabled={busy}
          onClick={() =>
            void run(() =>
              regenerate.mutateAsync({ userId, storyId: story.id }),
            )
          }
        >
          {t("companionAdmin.stories.regenerate")}
        </Button>
        <Button
          type="button"
          variant="danger"
          size="sm"
          disabled={busy}
          onClick={() => {
            if (window.confirm(t("companionAdmin.stories.deleteConfirm"))) {
              void run(
                () => remove.mutateAsync({ userId, storyId: story.id }),
                onClosed,
              );
            }
          }}
        >
          {t("companionAdmin.stories.delete")}
        </Button>
      </div>
    </article>
  );
}

function AccessRecord({ userId }: { readonly userId: number }) {
  const { t, formatDateTime } = useI18n();
  const log = useListCompanionAccessLogAdmin(userId, {
    query: { retry: false },
  });
  return (
    <section className="ca-subsection" aria-labelledby={`access-${userId}`}>
      <h4 id={`access-${userId}`}>
        {t("companionAdmin.companion.sections.access")}
      </h4>
      {(log.data ?? []).length === 0 ? (
        <p className="ca-empty">{t("companionAdmin.access.empty")}</p>
      ) : (
        <ol className="ca-access">
          {(log.data ?? []).slice(0, 30).map((row) => (
            <li key={row.id}>
              <time dateTime={row.at}>{formatDateTime(row.at)}</time>
              <span>
                {(
                  {
                    view_full_text: t(
                      "companionAdmin.access.actions.view_full_text",
                    ),
                    edit: t("companionAdmin.access.actions.edit"),
                    regenerate: t("companionAdmin.access.actions.regenerate"),
                    delete: t("companionAdmin.access.actions.delete"),
                    generate: t("companionAdmin.access.actions.generate"),
                    override: t("companionAdmin.access.actions.override"),
                    reset_progress: t(
                      "companionAdmin.access.actions.reset_progress",
                    ),
                    adjust_progress: t(
                      "companionAdmin.access.actions.adjust_progress",
                    ),
                  } as Record<string, string>
                )[row.action] ?? row.action}
                {row.companion_ref ? ` · ${row.companion_ref}` : ""}
                {row.story_id ? ` · #${row.story_id}` : ""}
              </span>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
