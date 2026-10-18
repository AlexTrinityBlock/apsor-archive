import type { ReactNode } from "react";

import { Icon } from "./Icon";

interface SectionHeadingProps {
  readonly index: string;
  readonly eyebrow: string;
  readonly title: string;
  readonly action?: ReactNode;
  readonly id?: string;
}

/** Numbered section masthead used across the home page and other shelves. */
export function SectionHeading({ index, eyebrow, title, action, id }: SectionHeadingProps) {
  return (
    <header className="section-heading">
      <div className="section-heading__index">
        <span className="section-heading__number">{index}</span>
        <Icon name="ring" size={17} />
      </div>
      <div className="section-heading__copy">
        <p className="eyebrow">{eyebrow}</p>
        <h2 id={id}>{title}</h2>
      </div>
      {action ? <div className="section-heading__action">{action}</div> : null}
    </header>
  );
}
