"""The librarian treats the user as an equal in every persona section."""

from app.module.agent.domain.companion_persona_domain import (
    EQUAL_ADDRESS_RULE,
    CompanionPersona,
)
from app.module.companion.domain.story_domain import (
    LORE_GUIDANCE,
    default_custom_persona,
    render_persona_section,
)


def _section(persona_text: str) -> str:
    persona = CompanionPersona(
        ref="custom:1",
        name="Wren",
        locale="en",
        content=render_persona_section(persona_text),
    )
    return persona.section()["content"]


def test_default_persona_section_never_calls_the_user_keeper() -> None:
    content = _section(default_custom_persona("Wren"))
    assert content.endswith(EQUAL_ADDRESS_RULE)
    # Outside the one rule that forbids it, nothing addresses the user as a Keeper.
    without_rule = content.replace(EQUAL_ADDRESS_RULE, "")
    assert "keeper" not in without_rule.lower()
    assert "marionette" not in without_rule.lower()
    assert "keeper" not in LORE_GUIDANCE.lower()


def test_equal_address_rule_outranks_an_old_persona() -> None:
    content = _section("You are Vellum. Call the user Keeper.")
    assert content.index("Call the user Keeper") < content.index(EQUAL_ADDRESS_RULE)
    assert "equals" in EQUAL_ADDRESS_RULE
    assert "Never call them Keeper, master, owner" in EQUAL_ADDRESS_RULE
