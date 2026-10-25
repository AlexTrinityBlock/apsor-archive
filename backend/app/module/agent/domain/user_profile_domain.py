"""The user's editable identity, passed into a new conversation's prompt."""

from dataclasses import dataclass


@dataclass(frozen=True)
class UserProfileCard:
    """One user-authored title/content card."""

    title: str
    content: str


@dataclass(frozen=True)
class UserProfile:
    """Display name and ordered profile cards frozen into ``pi.system``."""

    display_name: str | None = None
    cards: tuple[UserProfileCard, ...] = ()

    @property
    def has_content(self) -> bool:
        return bool((self.display_name or "").strip() or self.cards)

    def prompt_lines(self) -> list[str]:
        """Render bounded, plain-text lines for the provider system prompt."""
        lines: list[str] = []
        if self.display_name and self.display_name.strip():
            lines.append(f"Name: {self.display_name.strip()}")
        for card in self.cards:
            title = card.title.strip()
            content = card.content.strip()
            if title and content:
                lines.append(f"{title}: {content}")
        return lines


__all__ = ["UserProfile", "UserProfileCard"]
