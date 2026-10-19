import {
  useEffect,
  useId,
  useMemo,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type MouseEvent as ReactMouseEvent,
} from "react";
import { useNavigate } from "react-router-dom";

import { useScrollLock } from "../hook/useScrollLock";
import { Icon, type IconName } from "./Icon";
import { TreeMark } from "./TreeMark";

interface PalettePage {
  readonly to: string;
  readonly label: string;
  readonly description: string;
  readonly group: string;
  readonly icon: IconName;
  readonly keywords: readonly string[];
}

const PALETTE_PAGES: readonly PalettePage[] = [
  {
    to: "/",
    label: "Overview",
    description: "The archive at a glance",
    group: "Index",
    icon: "overview",
    keywords: ["home", "dashboard", "start"],
  },
  {
    to: "/search",
    label: "Search",
    description: "Hybrid search across every shelf",
    group: "Index",
    icon: "search",
    keywords: ["query", "find", "search_knowledge"],
  },
  {
    to: "/timeline",
    label: "Timeline",
    description: "Memories sampled through time",
    group: "Index",
    icon: "timeline",
    keywords: ["dates", "history", "read_timeline"],
  },
  {
    to: "/library",
    label: "File library",
    description: "Browse files and chunk windows",
    group: "Collections",
    icon: "library",
    keywords: ["files", "upload", "read_file"],
  },
  {
    to: "/tree",
    label: "Knowledge tree",
    description: "Walk the branching path index",
    group: "Collections",
    icon: "tree",
    keywords: ["paths", "folders", "read_path"],
  },
  {
    to: "/memory/latest",
    label: "Latest memory",
    description: "Read the newest record and its lineage",
    group: "Collections",
    icon: "memory",
    keywords: ["read_memory", "supersede", "trace"],
  },
  {
    to: "/memory/new",
    label: "Press a new memory",
    description: "Record a moment in the archive",
    group: "Collections",
    icon: "leaf",
    keywords: ["save_memory", "create", "write"],
  },
  {
    to: "/chat",
    label: "Chat",
    description: "A persistent thread with its sources and tool steps",
    group: "Studio",
    icon: "chat",
    keywords: ["conversation", "transcript", "agent", "thread", "citations"],
  },
  {
    to: "/questions",
    label: "Questions",
    description: "Saved questions, answers, and citations",
    group: "Studio",
    icon: "quote",
    keywords: ["saved", "book", "ask later", "question bank"],
  },
  {
    to: "/ask",
    label: "Quick ask",
    description: "One grounded answer with citations",
    group: "Studio",
    icon: "ask",
    keywords: ["ai", "rag", "question", "deepseek"],
  },
  {
    to: "/method",
    label: "Method",
    description: "How the archive is built",
    group: "Studio",
    icon: "method",
    keywords: ["essay", "architecture", "hybrid", "bm25"],
  },
  {
    to: "/settings",
    label: "Settings",
    description: "Theme, AI status, and system",
    group: "Studio",
    icon: "settings",
    keywords: ["preferences", "night", "paper", "api"],
  },
];

interface CommandPaletteProps {
  readonly onClose: () => void;
  readonly memoryHref: string;
}

/**
 * Cmd+K / Ctrl+K navigation palette.
 *
 * The component is mounted only while open, so each opening starts with a clean
 * query. Focus starts in the input, the list follows the active descendant, and
 * Tab cycles between the input and the close control.
 */
export function CommandPalette({ onClose, memoryHref }: CommandPaletteProps) {
  const navigate = useNavigate();
  const dialogRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const dialogTitleId = useId();
  const listId = useId();

  useScrollLock(true);

  useEffect(() => {
    const previous = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    const frame = window.requestAnimationFrame(() => inputRef.current?.focus());
    return () => {
      window.cancelAnimationFrame(frame);
      previous?.focus();
    };
  }, []);

  const results = useMemo(() => {
    const pages = PALETTE_PAGES.map((page) =>
      page.to === "/memory/latest" ? { ...page, to: memoryHref } : page,
    );
    const needle = query.trim().toLowerCase();
    if (needle.length === 0) {
      return pages;
    }
    return pages.filter((page) =>
      [page.label, page.description, page.group, page.to, ...page.keywords].some((value) =>
        value.toLowerCase().includes(needle),
      ),
    );
  }, [memoryHref, query]);

  const boundedIndex =
    results.length === 0 ? 0 : Math.min(activeIndex, Math.max(results.length - 1, 0));
  const activePage = results[boundedIndex];

  const goTo = (page: PalettePage) => {
    navigate(page.to);
    onClose();
  };

  const handleKeyDown = (event: ReactKeyboardEvent<HTMLDivElement>) => {
    if (event.key === "Escape") {
      event.preventDefault();
      onClose();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActiveIndex((current) =>
        results.length === 0 ? 0 : (Math.min(current, results.length - 1) + 1) % results.length,
      );
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((current) => {
        if (results.length === 0) {
          return 0;
        }
        const base = Math.min(current, results.length - 1);
        return (base - 1 + results.length) % results.length;
      });
      return;
    }
    if (event.key === "Enter" && activePage) {
      event.preventDefault();
      goTo(activePage);
      return;
    }
    if (event.key === "Tab") {
      const focusables = Array.from(
        dialogRef.current?.querySelectorAll<HTMLElement>(
          'button:not([disabled]):not([tabindex="-1"]), input, a[href]',
        ) ?? [],
      ).filter((element) => element.offsetParent !== null);
      if (focusables.length === 0) {
        return;
      }
      const first = focusables[0];
      const last = focusables[focusables.length - 1];
      if (!first || !last) {
        return;
      }
      if (event.shiftKey && document.activeElement === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault();
        first.focus();
      }
    }
  };

  const handleBackdrop = (event: ReactMouseEvent<HTMLDivElement>) => {
    if (event.target === event.currentTarget) {
      onClose();
    }
  };

  return (
    <div className="palette-layer" onMouseDown={handleBackdrop} data-testid="command-palette">
      <div
        ref={dialogRef}
        className="palette"
        role="dialog"
        aria-modal="true"
        aria-labelledby={dialogTitleId}
        onKeyDown={handleKeyDown}
      >
        <div className="palette__head">
          <span className="palette__seal" aria-hidden="true">
            <TreeMark size={30} />
          </span>
          <div className="palette__heading">
            <p className="eyebrow">Archive index</p>
            <h2 id={dialogTitleId}>Jump to a page</h2>
          </div>
          <button type="button" className="palette__close" onClick={onClose} aria-label="Close command palette">
            <Icon name="close" size={17} />
          </button>
        </div>

        <div className="palette__query">
          <Icon name="search" size={19} />
          <label className="visually-hidden" htmlFor={`${listId}-input`}>
            Search pages and tools
          </label>
          <input
            ref={inputRef}
            id={`${listId}-input`}
            type="text"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActiveIndex(0);
            }}
            placeholder="Search pages and tools..."
            autoComplete="off"
            spellCheck={false}
            role="combobox"
            aria-expanded="true"
            aria-controls={listId}
            aria-autocomplete="list"
            aria-activedescendant={
              activePage ? `${listId}-option-${boundedIndex}` : undefined
            }
          />
          <kbd className="keycap">ESC</kbd>
        </div>

        <div className="palette__list" id={listId} role="listbox" aria-label="Pages">
          {results.length === 0 ? (
            <div
              className="palette__empty"
              role="option"
              aria-disabled="true"
              aria-selected="false"
              tabIndex={-1}
            >
              No page matches “{query.trim()}”. Try “memory” or “method”.
            </div>
          ) : (
            results.map((page, index) => (
              <button
                key={page.to}
                id={`${listId}-option-${index}`}
                type="button"
                role="option"
                aria-selected={index === boundedIndex}
                tabIndex={-1}
                className={index === boundedIndex ? "palette__item is-active" : "palette__item"}
                onMouseEnter={() => setActiveIndex(index)}
                onClick={() => goTo(page)}
              >
                <span className="palette__item-icon" aria-hidden="true">
                  <Icon name={page.icon} size={18} />
                </span>
                <span className="palette__item-copy">
                  <span className="palette__item-label">{page.label}</span>
                  <span className="palette__item-description">{page.description}</span>
                </span>
                <span className="palette__item-group">{page.group}</span>
                <Icon name="arrow-right" size={16} className="palette__item-arrow" />
              </button>
            ))
          )}
        </div>

        <div className="palette__foot">
          <span>
            <kbd className="keycap">↑</kbd>
            <kbd className="keycap">↓</kbd> to move
          </span>
          <span>
            <kbd className="keycap">↵</kbd> to open
          </span>
          <span className="palette__foot-brand">DENDROMATRIX · INDEX</span>
        </div>
      </div>
    </div>
  );
}
