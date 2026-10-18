import { useId, type ComponentPropsWithoutRef, type ReactNode } from "react";

type PanelTone = "paper" | "plain" | "moss" | "ink";

interface PanelProps extends Omit<ComponentPropsWithoutRef<"section">, "title"> {
  readonly eyebrow?: string;
  readonly title?: ReactNode;
  readonly action?: ReactNode;
  readonly footer?: ReactNode;
  readonly tone?: PanelTone;
  readonly padded?: boolean;
  readonly corners?: boolean;
}

/** A paper surface with an archival eyebrow, title, and optional footer. */
export function Panel({
  eyebrow,
  title,
  action,
  footer,
  tone = "paper",
  padded = true,
  corners = false,
  className,
  children,
  ...rest
}: PanelProps) {
  const headingId = useId();
  const classes = [
    "panel",
    `panel--${tone}`,
    padded ? "panel--padded" : null,
    corners ? "panel--corners" : null,
    className,
  ]
    .filter(Boolean)
    .join(" ");

  return (
    <section className={classes} aria-labelledby={title ? headingId : undefined} {...rest}>
      {eyebrow || title || action ? (
        <header className="panel__header">
          <div className="panel__heading">
            {eyebrow ? <p className="eyebrow">{eyebrow}</p> : null}
            {title ? (
              <h2 className="panel__title" id={headingId}>
                {title}
              </h2>
            ) : null}
          </div>
          {action ? <div className="panel__action">{action}</div> : null}
        </header>
      ) : null}
      <div className="panel__body">{children}</div>
      {footer ? <footer className="panel__footer">{footer}</footer> : null}
    </section>
  );
}
