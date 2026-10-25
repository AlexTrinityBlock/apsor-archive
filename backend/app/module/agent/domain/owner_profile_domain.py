"""The owner's editable identity, passed into a new conversation's prompt."""

from dataclasses import dataclass


@dataclass(frozen=True)
class OwnerProfile:
    """Display name and self-introduction frozen into ``pi.system``."""

    display_name: str | None = None
    bio: str | None = None

    @property
    def has_content(self) -> bool:
        return bool((self.display_name or "").strip() or (self.bio or "").strip())

    def prompt_lines(self) -> list[str]:
        """Render bounded, plain-text lines for the provider system prompt."""
        lines: list[str] = []
        if self.display_name and self.display_name.strip():
            lines.append(f"Name: {self.display_name.strip()}")
        if self.bio and self.bio.strip():
            lines.append(f"Self-introduction: {self.bio.strip()}")
        return lines


__all__ = ["OwnerProfile"]
