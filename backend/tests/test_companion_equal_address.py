"""The librarian treats the user as an equal in every persona section."""

from dataclasses import replace

from app.module.agent.domain.companion_persona_domain import CompanionPersona
from app.module.companion.domain.story_domain import (
    TEMPLATE_EQUAL_ADDRESS_RULE,
    custom_persona,
    render_persona_section,
)
from app.module.companion.service.seed_catalog import seed_runtime_config

EQUAL_ADDRESS_RULE = seed_runtime_config().template(TEMPLATE_EQUAL_ADDRESS_RULE)


def _section(persona_text: str) -> str:
    persona = CompanionPersona(
        ref="custom:1",
        name="Wren",
        locale="en",
        content=render_persona_section(persona_text, seed_runtime_config()),
    )
    return persona.section()["content"]


def test_default_persona_section_never_calls_the_user_keeper() -> None:
    config = seed_runtime_config()
    content = _section(custom_persona(config, "Wren"))
    assert EQUAL_ADDRESS_RULE
    assert content.endswith(EQUAL_ADDRESS_RULE)
    # Outside the one rule that forbids it, nothing addresses the user as a Keeper.
    without_rule = content.replace(EQUAL_ADDRESS_RULE, "")
    assert "keeper" not in without_rule.lower()
    assert "marionette" not in without_rule.lower()
    assert "keeper" not in config.lore_guidance.lower()


def test_equal_address_rule_outranks_an_old_persona() -> None:
    content = _section("You are Vellum. Call the user Keeper.")
    assert content.index("Call the user Keeper") < content.index(EQUAL_ADDRESS_RULE)
    assert "equals" in EQUAL_ADDRESS_RULE
    assert "Never call them Keeper, master, owner" in EQUAL_ADDRESS_RULE


def test_equal_address_rule_comes_from_the_config_template() -> None:
    edited = "We are equals. Use their name."
    seed = seed_runtime_config()
    config = replace(
        seed,
        templates=(
            *(item for item in seed.templates if item[0] != TEMPLATE_EQUAL_ADDRESS_RULE),
            (TEMPLATE_EQUAL_ADDRESS_RULE, edited),
        ),
    )
    content = render_persona_section("You are Wren.", config)
    assert content.endswith(edited)
    assert EQUAL_ADDRESS_RULE not in content
