import { Link } from "react-router-dom";

import type { ToolDemo, ToolName } from "../type/demo";
import { Icon, type IconName } from "./Icon";

const TOOL_ICONS: Record<ToolName, IconName> = {
  search_knowledge: "search",
  read_file: "file",
  read_timeline: "timeline",
  read_path: "branch",
  save_memory: "leaf",
  read_memory: "memory",
};

/** A numbered catalogue card for one of the archive's six retrieval tools. */
export function ToolCard({ tool }: { readonly tool: ToolDemo }) {
  return (
    <Link className={`tool-card tool-card--${tool.accent}`} to={tool.href}>
      <span className="tool-card__top">
        <span className="tool-card__index">{tool.index}</span>
        <span className="tool-card__icon" aria-hidden="true">
          <Icon name={TOOL_ICONS[tool.name]} size={20} />
        </span>
        <span className={`tool-card__method tool-card__method--${tool.method.toLowerCase()}`}>
          {tool.method}
        </span>
      </span>
      <span className="tool-card__name">{tool.name}</span>
      <span className="tool-card__title">{tool.title}</span>
      <span className="tool-card__description">{tool.description}</span>
      <span className="tool-card__foot">
        <code>{tool.endpoint}</code>
        <Icon name="arrow-up-right" size={16} />
      </span>
    </Link>
  );
}
