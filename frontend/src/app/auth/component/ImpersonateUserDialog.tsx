import {
  useEffect,
  useId,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useNavigate } from "react-router-dom";

import { Badge } from "../../component/Badge";
import { Button } from "../../component/Button";
import { EmptyState } from "../../component/EmptyState";
import { Icon } from "../../component/Icon";
import { Loader } from "../../component/Loader";
import { useListAccounts } from "../../generated-apis-types";
import type { AccountSchema } from "../../generated-apis-types/schemas";
import { useScrollLock } from "../../hook/useScrollLock";
import { useApiErrorMessage, useI18n } from "../../i18n";
import { useAuth } from "../AuthProvider";
import "../auth.css";

interface ImpersonateUserDialogProps {
  readonly onClose: () => void;
}

const FOCUSABLE =
  'a[href], button:not([disabled]), input:not([disabled]), textarea:not([disabled]), select:not([disabled]), [tabindex]:not([tabindex="-1"])';

function accountName(account: AccountSchema): string {
  return account.display_name ?? account.username;
}

function initialsFor(name: string): string {
  return Array.from(name.trim()).slice(0, 2).join("").toUpperCase() || "?";
}

function matchesSearch(account: AccountSchema, term: string): boolean {
  if (term.length === 0) {
    return true;
  }
  const displayName = (account.display_name ?? "").toLocaleLowerCase();
  return (
    displayName.includes(term) ||
    account.username.toLocaleLowerCase().includes(term)
  );
}

/**
 * Root-only user switcher opened from the rail footer. It lists normal
 * accounts, searches locally, and starts an impersonation session. The dialog
 * is only mounted while root is not already impersonating.
 */
export function ImpersonateUserDialog({
  onClose,
}: ImpersonateUserDialogProps) {
  const { t, formatNumber } = useI18n();
  const { user, impersonate } = useAuth();
  const navigate = useNavigate();
  const apiErrorMessage = useApiErrorMessage();
  const titleId = useId();
  const descriptionId = useId();
  const searchId = useId();
  const searchRef = useRef<HTMLInputElement>(null);
  const dialogRef = useRef<HTMLDivElement>(null);
  const onCloseRef = useRef(onClose);
  const [search, setSearch] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submittingUserId, setSubmittingUserId] = useState<number | null>(null);
  const busy = submittingUserId !== null;

  const query = useListAccounts({
    query: { enabled: true, retry: false, staleTime: 15_000 },
  });

  useScrollLock(true);

  useEffect(() => {
    onCloseRef.current = onClose;
  }, [onClose]);

  useEffect(() => {
    const previous =
      document.activeElement instanceof HTMLElement
        ? document.activeElement
        : null;
    searchRef.current?.focus();
    return () => {
      previous?.focus();
    };
  }, []);

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape" && !busy) {
        event.preventDefault();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") {
        return;
      }
      const dialog = dialogRef.current;
      if (!dialog) {
        return;
      }
      const focusable = Array.from(
        dialog.querySelectorAll<HTMLElement>(FOCUSABLE),
      ).filter((element) => element.offsetParent !== null);
      if (focusable.length === 0) {
        event.preventDefault();
        dialog.focus();
        return;
      }
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [busy]);

  const currentUserId = user?.user_id ?? null;
  const term = search.trim().toLocaleLowerCase();
  const accounts = (query.data?.items ?? []).filter(
    (account) =>
      account.role !== "root" &&
      (currentUserId === null || account.user_id !== currentUserId),
  );
  const filtered = accounts.filter((account) => matchesSearch(account, term));

  const handleImpersonate = async (account: AccountSchema) => {
    if (busy || !account.is_active || account.must_change_password) {
      return;
    }
    setError(null);
    setSubmittingUserId(account.user_id);
    try {
      await impersonate(account.user_id);
      onClose();
      navigate("/chat");
    } catch (caught) {
      setError(apiErrorMessage(caught, "core.impersonation.error"));
    } finally {
      setSubmittingUserId(null);
    }
  };

  let list: ReactNode;
  if (query.isPending) {
    list = (
      <div className="impersonate-dialog__state">
        <Loader size={28} label={t("core.impersonation.loading")} />
      </div>
    );
  } else if (query.isError) {
    list = (
      <div className="impersonate-dialog__state" role="alert">
        <span className="impersonate-dialog__state-icon" aria-hidden="true">
          <Icon name="info" size={18} />
        </span>
        <p>{apiErrorMessage(query.error, "core.impersonation.loadError")}</p>
        <Button
          type="button"
          variant="ghost"
          size="sm"
          onClick={() => void query.refetch()}
          disabled={query.isFetching}
        >
          <Icon name="ring" size={14} />
          {query.isFetching
            ? t("core.common.retrying")
            : t("core.common.retry")}
        </Button>
      </div>
    );
  } else if (accounts.length === 0) {
    list = (
      <EmptyState
        icon="users"
        title={t("core.impersonation.noAccounts")}
        description={t("core.impersonation.noAccountsDescription")}
        className="impersonate-dialog__empty"
      />
    );
  } else if (filtered.length === 0) {
    list = (
      <EmptyState
        icon="search"
        title={t("core.impersonation.noMatches")}
        description={t("core.impersonation.noMatchesDescription")}
        className="impersonate-dialog__empty"
      />
    );
  } else {
    list = (
      <ul
        className="impersonate-dialog__list"
        aria-label={t("core.impersonation.dialogTitle")}
      >
        {filtered.map((account) => {
          const name = accountName(account);
          const eligible =
            account.is_active && !account.must_change_password;
          let reason: string | null = null;
          if (!account.is_active) {
            reason = t("core.impersonation.disabledReason");
          } else if (account.must_change_password) {
            reason = t("core.impersonation.mustChangeReason");
          }
          return (
            <li key={account.user_id} className="impersonate-dialog__row">
              <div className="impersonate-dialog__row-head">
                <div className="impersonate-dialog__identity">
                  <span
                    className="impersonate-dialog__avatar"
                    aria-hidden="true"
                  >
                    {initialsFor(name)}
                  </span>
                  <span className="impersonate-dialog__identity-copy">
                    <strong>{name}</strong>
                    <span>@{account.username}</span>
                  </span>
                </div>
                <div className="impersonate-dialog__usage">
                  <span className="impersonate-dialog__metric">
                    <span>{t("core.accounts.totalTokens")}</span>
                    <strong>{formatNumber(account.usage.total_tokens)}</strong>
                  </span>
                  <span className="impersonate-dialog__metric">
                    <span>{t("core.accounts.apiCalls")}</span>
                    <strong>{formatNumber(account.usage.api_calls)}</strong>
                  </span>
                </div>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => void handleImpersonate(account)}
                  disabled={busy || !eligible}
                  aria-label={t("core.impersonation.impersonateUser", {
                    name,
                  })}
                  className="impersonate-dialog__action"
                >
                  {busy && submittingUserId === account.user_id
                    ? t("core.impersonation.impersonating")
                    : t("core.impersonation.impersonate")}
                </Button>
              </div>
              <div className="impersonate-dialog__row-meta">
                <Badge tone={account.is_active ? "moss" : "neutral"} dot>
                  {account.is_active
                    ? t("core.accounts.active")
                    : t("core.accounts.disabled")}
                </Badge>
                {account.must_change_password ? (
                  <Badge tone="ochre">{t("core.accounts.mustChange")}</Badge>
                ) : null}
                {reason ? (
                  <span className="impersonate-dialog__reason">{reason}</span>
                ) : null}
              </div>
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <div
      className="modal"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) {
          onClose();
        }
      }}
    >
      <div
        ref={dialogRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        aria-describedby={descriptionId}
        aria-busy={busy}
        tabIndex={-1}
        className="modal-dialog modal-dialog--md impersonate-dialog"
      >
        <header className="modal-head impersonate-dialog__head">
          <div className="impersonate-dialog__heading">
            <p className="eyebrow">{t("core.impersonation.eyebrow")}</p>
            <h2 className="modal-title" id={titleId}>
              {t("core.impersonation.dialogTitle")}
            </h2>
          </div>
          <button
            type="button"
            className="modal-btn-close"
            onClick={onClose}
            disabled={busy}
            aria-label={t("core.common.close")}
          >
            <Icon name="close" size={18} />
          </button>
        </header>
        <div className="modal-body modal-body--plain impersonate-dialog__body">
          <p className="impersonate-dialog__description" id={descriptionId}>
            {t("core.impersonation.dialogDescription")}
          </p>

          <div className="impersonate-dialog__search">
            <span className="impersonate-dialog__search-icon" aria-hidden="true">
              <Icon name="search" size={16} />
            </span>
            <label className="visually-hidden" htmlFor={searchId}>
              {t("core.impersonation.searchLabel")}
            </label>
            <input
              ref={searchRef}
              id={searchId}
              type="search"
              value={search}
              onChange={(event) => setSearch(event.target.value)}
              placeholder={t("core.impersonation.searchPlaceholder")}
              autoComplete="off"
              spellCheck={false}
              disabled={busy}
              className="impersonate-dialog__input"
            />
          </div>

          {error ? (
            <p className="impersonate-dialog__error" role="alert">
              <Icon name="info" size={15} />
              {error}
            </p>
          ) : null}

          <div className="impersonate-dialog__list-wrap">{list}</div>
        </div>
      </div>
    </div>
  );
}
