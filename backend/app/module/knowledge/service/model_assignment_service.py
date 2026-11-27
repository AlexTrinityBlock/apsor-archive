"""Assignment reads, writes, probe gating, and endpoint/catalog discovery.

The service is the only place that decides whether an assignment may be saved.
It validates both endpoint rows on every ``PUT`` (active, non-``none``, keyed),
compares a connection fingerprint per slot, probes only the slots whose
fingerprint changed, and writes all eight columns once after every changed slot
succeeds. A failed probe rejects the whole write with nothing persisted.

Reads are advisory: an inactive or deleted endpoint is reported as
``degraded_reason`` rather than an error, and warnings never block a write. The
budget columns are returned as stored; ``None`` means "inherit the agent
runtime default".
"""

from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from sqlalchemy.ext.asyncio import AsyncSession

from app.infrastructure.ai.model_catalog import (
    MODEL_CATALOG,
    TIER_ORDER,
    ModelPrices,
    spec_for,
)
from app.infrastructure.ai.probe import ProbeOutcome, ProviderProbe
from app.infrastructure.ai.runtime import AiRuntime
from app.infrastructure.ai.user_models import (
    DEFAULT_AUXILIARY_EFFORT,
    ChatAssignment,
    SlotValues,
    assignment_fingerprint,
    resolve_endpoint,
    slot_values,
)
from app.module.auth.exception.domain_error import AccountNotFoundError
from app.module.auth.model.auth_model import AppUserModel
from app.module.knowledge.domain.provider_config_domain import (
    CHAT_TABLE_SPEC,
    default_base_url_for,
)
from app.module.knowledge.domain.provider_runtime_domain import ProviderConfig, ProviderDefaults
from app.module.knowledge.exception.domain_error import (
    InvalidModelAssignmentError,
    ModelProbeFailedError,
    ProviderNotFoundError,
)
from app.module.knowledge.model.provider_config_model import ChatProviderConfigModel
from app.module.knowledge.repository.model_assignment_repository import (
    AccountAssignment,
    ModelAssignmentRepository,
)
from app.module.knowledge.schema.model_assignment_schema import (
    ChatEndpointListSchema,
    ChatEndpointProbeResultSchema,
    ChatEndpointProbeSchema,
    ChatEndpointSchema,
    EndpointKeySource,
    ModelAssignmentListSchema,
    ModelAssignmentSchema,
    ModelAssignmentUpdateSchema,
    ModelCatalogEntrySchema,
    ModelCatalogListSchema,
    ModelPricingSchema,
)


class ModelAssignmentService:
    """Coordinate one assignment request over one database session."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        repository: ModelAssignmentRepository,
        runtime: AiRuntime,
        defaults: ProviderDefaults,
        probe: ProviderProbe,
    ) -> None:
        self.session = session
        self.repository = repository
        self.runtime = runtime
        self.defaults = defaults
        self.probe = probe

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    async def list_assignments(self) -> ModelAssignmentListSchema:
        """Return every account and its assignment in one query."""
        accounts = await self.repository.list_account_assignments()
        row_ids = {
            row_id
            for account in accounts
            for row_id in (
                account.chat_provider_config_id,
                account.aux_provider_config_id,
            )
            if row_id is not None
        }
        chat_rows = await self.repository.get_chat_rows(row_ids)
        chain = self._chain_index()
        return ModelAssignmentListSchema(
            items=[
                self._read(
                    assignment=self._assignment_from_account_row(account),
                    username=account.username,
                    updated_at=account.updated_at,
                    chat_rows=chat_rows,
                    chain=chain,
                )
                for account in accounts
            ]
        )

    async def get_assignment(self, user_id: int) -> ModelAssignmentSchema:
        """Return one account assignment; an unknown account is a 404."""
        account = await self.repository.get_account(user_id)
        if account is None:
            raise AccountNotFoundError(user_id)
        return await self._read_account(account)

    async def get_my_assignment(self, user_id: int) -> ModelAssignmentSchema:
        """Return the caller's own assignment; authenticated but not root-only."""
        return await self.get_assignment(user_id)

    # ------------------------------------------------------------------
    # Writes
    # ------------------------------------------------------------------

    async def update_assignment(
        self,
        user_id: int,
        payload: ModelAssignmentUpdateSchema,
    ) -> ModelAssignmentSchema:
        """Validate, probe changed slots, then write all eight columns once."""
        account = await self.repository.lock_account(user_id)
        if account is None:
            raise AccountNotFoundError(user_id)
        self._validate_budget_pair(payload)

        stored = self._assignment_from_account_model(account)
        stored_ids = {
            values.row_id
            for values in (
                slot_values(stored, "primary"),
                slot_values(stored, "auxiliary"),
            )
            if values.row_id is not None
        }
        chat_rows = await self.repository.get_chat_rows(
            stored_ids
            | {payload.chat_provider_config_id, payload.aux_provider_config_id}
        )
        primary_row = self._require_usable_row(
            chat_rows,
            payload.chat_provider_config_id,
            "primary",
        )
        auxiliary_row = self._require_usable_row(
            chat_rows,
            payload.aux_provider_config_id,
            "auxiliary",
        )
        self._require_keyed_row(primary_row, "primary")
        self._require_keyed_row(auxiliary_row, "auxiliary")

        stored_primary = self._stored_fingerprint(
            slot_values(stored, "primary"),
            chat_rows,
        )
        stored_auxiliary = self._stored_fingerprint(
            slot_values(stored, "auxiliary"),
            chat_rows,
        )
        primary_fingerprint = self._fingerprint(
            primary_row,
            payload.chat_model,
            payload.chat_reasoning_effort,
        )
        auxiliary_fingerprint = self._fingerprint(
            auxiliary_row,
            payload.aux_model,
            payload.aux_reasoning_effort,
        )

        changed_slots = (
            (
                "primary",
                primary_row,
                payload.chat_model,
                payload.chat_reasoning_effort,
                primary_fingerprint != stored_primary,
            ),
            (
                "auxiliary",
                auxiliary_row,
                payload.aux_model,
                payload.aux_reasoning_effort,
                auxiliary_fingerprint != stored_auxiliary,
            ),
        )
        # A shared endpoint with the same model and effort is one connection,
        # so it is tested once even when both slots changed.
        probed: dict[tuple[int, str, str | None], ProbeOutcome] = {}
        for slot, row, model, effort, changed in changed_slots:
            if not changed:
                continue
            probe_key = (row.id, model, effort)
            outcome = probed.get(probe_key)
            if outcome is None:
                resolved = self._resolve_usable_config(row, slot)
                outcome = await self.probe.probe(
                    resolved,
                    model=model,
                    reasoning_effort=effort,
                )
                probed[probe_key] = outcome
            if not outcome.ok:
                raise ModelProbeFailedError(
                    slot,
                    outcome.detail or "the provider probe failed.",
                )

        await self.repository.write_assignment(
            user_id,
            chat_provider_config_id=payload.chat_provider_config_id,
            chat_model=payload.chat_model,
            chat_reasoning_effort=payload.chat_reasoning_effort,
            aux_provider_config_id=payload.aux_provider_config_id,
            aux_model=payload.aux_model,
            aux_reasoning_effort=payload.aux_reasoning_effort,
            chat_context_window_tokens=payload.context_window_tokens,
            chat_compaction_threshold_tokens=payload.compaction_threshold_tokens,
        )
        return await self.get_assignment(user_id)

    async def reset_assignment(self, user_id: int) -> ModelAssignmentSchema:
        """Clear both assignments, keeping the NOT NULL auxiliary effort."""
        account = await self.repository.lock_account(user_id)
        if account is None:
            raise AccountNotFoundError(user_id)
        await self.repository.write_assignment(
            user_id,
            chat_provider_config_id=None,
            chat_model=None,
            chat_reasoning_effort=None,
            aux_provider_config_id=None,
            aux_model=None,
            aux_reasoning_effort=DEFAULT_AUXILIARY_EFFORT,
            chat_context_window_tokens=None,
            chat_compaction_threshold_tokens=None,
        )
        return await self.get_assignment(user_id)

    # ------------------------------------------------------------------
    # Endpoint discovery and probing
    # ------------------------------------------------------------------

    async def list_chat_endpoints(self) -> ChatEndpointListSchema:
        """Return saved chat rows with a host name only, never a full URL or key."""
        rows = await self.repository.list_chat_rows()
        return ChatEndpointListSchema(items=[self._endpoint_schema(row) for row in rows])

    def _endpoint_schema(self, row: ChatProviderConfigModel) -> ChatEndpointSchema:
        key_source = self._key_source(row)
        return ChatEndpointSchema(
            id=row.id,
            label=row.label or row.provider,
            provider=row.provider,
            model=row.model,
            base_url_host=self._base_url_host(row),
            configured=row.provider != "none" and key_source != "none",
            key_source=key_source,
            is_active=row.is_active,
            priority=row.priority,
            max_output_tokens=row.max_output_tokens,
        )

    async def list_chat_models(self) -> ModelCatalogListSchema:
        """Return the advisory catalog in escalation order."""
        specs = sorted(
            MODEL_CATALOG.values(),
            key=lambda spec: (
                TIER_ORDER.index(spec.tier) if spec.tier is not None else len(TIER_ORDER),
                spec.model,
            ),
        )
        return ModelCatalogListSchema(
            items=[
                ModelCatalogEntrySchema(
                    model=spec.model,
                    display_name=spec.display_name,
                    provider=spec.provider,
                    tier=spec.tier,
                    context_window_tokens=spec.context_window_tokens,
                    max_output_tokens=spec.max_output_tokens,
                    supports_tools=spec.supports_tools,
                    supports_vision=spec.supports_vision,
                    pricing=self._pricing(spec.prices),
                    suggested_compaction_tokens=spec.suggested_compaction_tokens,
                    status=spec.status,
                    replacement_model=spec.replacement_model,
                )
                for spec in specs
            ]
        )

    async def probe_chat_endpoint(
        self,
        provider_config_id: int,
        payload: ChatEndpointProbeSchema,
    ) -> ChatEndpointProbeResultSchema:
        """Test one candidate model/effort and never write anything.

        An unknown row is a 404 because the caller addressed something that does
        not exist. Every other unusable state and every provider failure returns
        HTTP 200 with ``ok=false`` so the dialog can render the reason.
        """
        row = (await self.repository.get_chat_rows({provider_config_id})).get(
            provider_config_id
        )
        if row is None:
            raise ProviderNotFoundError(provider_config_id)
        if not row.is_active:
            return self._probe_failure("the endpoint is not active.")
        if row.provider == "none":
            return self._probe_failure("the endpoint is disabled.")
        if self._key_source(row) == "none":
            return self._probe_failure("the endpoint has no API key.")
        resolved = resolve_endpoint(self.runtime.chat_chain, provider_config_id)
        if (
            resolved is None
            or not resolved.enabled
            or resolved.provider == "none"
            or not resolved.api_key
        ):
            return self._probe_failure("the endpoint has no usable API key.")
        outcome = await self.probe.probe(
            resolved,
            model=payload.model,
            reasoning_effort=payload.reasoning_effort,
        )
        return ChatEndpointProbeResultSchema(
            ok=outcome.ok,
            latency_ms=outcome.latency_ms,
            resolved_model=outcome.resolved_model,
            usage=outcome.usage,
            detail=outcome.detail,
        )

    # ------------------------------------------------------------------
    # Validation helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _validate_budget_pair(payload: ModelAssignmentUpdateSchema) -> None:
        """Enforce ``threshold < window`` when both are explicit.

        When only the threshold is stored, the comparison is against the
        inherited global window, which lives in the agent slice; the agent
        runtime reports that combination as ``invalid_threshold`` instead of
        rewriting the operator's value here.
        """
        threshold = payload.compaction_threshold_tokens
        window = payload.context_window_tokens
        if threshold is not None and window is not None and threshold >= window:
            raise InvalidModelAssignmentError(
                "compaction_threshold_tokens must be less than context_window_tokens."
            )

    @staticmethod
    def _require_usable_row(
        chat_rows: dict[int, ChatProviderConfigModel],
        row_id: int,
        slot: str,
    ) -> ChatProviderConfigModel:
        """Validate one endpoint row on every write, probe or not."""
        row = chat_rows.get(row_id)
        if row is None:
            raise InvalidModelAssignmentError(
                f"{slot}: the selected endpoint no longer exists."
            )
        if not row.is_active:
            raise InvalidModelAssignmentError(
                f"{slot}: the selected endpoint is not active."
            )
        if row.provider == "none":
            raise InvalidModelAssignmentError(
                f"{slot}: the selected endpoint is disabled."
            )
        return row

    def _require_keyed_row(
        self,
        row: ChatProviderConfigModel,
        slot: str,
    ) -> None:
        """Reject a row without a database or provider-scoped environment key.

        This check runs on every ``PUT`` for both slots, including a budget-only
        save where no probe is needed. A corrupt ciphertext is only detectable by
        a probe, so a changed slot additionally resolves its key from the
        runtime chain before testing.
        """
        if self._key_source(row) == "none":
            raise InvalidModelAssignmentError(
                f"{slot}: the selected endpoint has no API key."
            )

    def _resolve_usable_config(
        self,
        row: ChatProviderConfigModel,
        slot: str,
    ) -> ProviderConfig:
        """Return the runtime config that carries this row's resolved key."""
        resolved = resolve_endpoint(self.runtime.chat_chain, row.id)
        if (
            resolved is None
            or not resolved.enabled
            or resolved.provider == "none"
            or not resolved.api_key
        ):
            raise InvalidModelAssignmentError(
                f"{slot}: the selected endpoint has no usable API key."
            )
        return resolved

    def _key_source(self, row: ChatProviderConfigModel) -> EndpointKeySource:
        """Report where this row's key would come from, matching ``AiRuntime``."""
        if row.api_key_ciphertext:
            return "database"
        if self._environment_key(row.provider):
            return "environment"
        return "none"

    def _environment_key(self, provider: str) -> str | None:
        """Provider-scoped chat fallback; never a cross-provider key."""
        if provider == "anthropic":
            return self.defaults.anthropic_api_key
        if provider == "deepseek":
            return self.defaults.deepseek_api_key
        return None

    # ------------------------------------------------------------------
    # Fingerprints
    # ------------------------------------------------------------------

    def _fingerprint(
        self,
        row: ChatProviderConfigModel,
        model: str,
        effort: str | None,
    ) -> str:
        """Hash one candidate connection using the stored ciphertext."""
        return assignment_fingerprint(
            self._fingerprint_config(row),
            model,
            effort,
            api_key_ciphertext=row.api_key_ciphertext or "",
        )

    def _stored_fingerprint(
        self,
        values: SlotValues,
        chat_rows: dict[int, ChatProviderConfigModel],
    ) -> str | None:
        """Return the stored slot fingerprint, or ``None`` when it cannot exist."""
        if values.row_id is None or not values.model:
            return None
        row = chat_rows.get(values.row_id)
        if row is None:
            return None
        return self._fingerprint(row, values.model, values.effort)

    @staticmethod
    def _fingerprint_config(row: ChatProviderConfigModel) -> ProviderConfig:
        """Project the identity fields a fingerprint needs; no key is carried."""
        return ProviderConfig(
            capability="chat",
            provider=row.provider,
            label=row.label or row.provider,
            model=row.model,
            base_url=row.base_url,
            api_key=None,
            dimension=None,
            enabled=row.is_active,
            source="database",
            row_id=row.id,
        )

    # ------------------------------------------------------------------
    # Read projection
    # ------------------------------------------------------------------

    async def _read_account(self, account: AppUserModel) -> ModelAssignmentSchema:
        assignment = self._assignment_from_account_model(account)
        chat_rows = await self.repository.get_chat_rows(
            row_id
            for row_id in (assignment.provider_config_id, assignment.aux_provider_config_id)
            if row_id is not None
        )
        return self._read(
            assignment=assignment,
            username=account.username,
            updated_at=account.updated_at,
            chat_rows=chat_rows,
            chain=self._chain_index(),
        )

    def _read(
        self,
        *,
        assignment: ChatAssignment,
        username: str,
        updated_at: datetime,
        chat_rows: dict[int, ChatProviderConfigModel],
        chain: dict[int, ProviderConfig],
    ) -> ModelAssignmentSchema:
        """Project one stored assignment into stored, effective, and warning fields."""
        primary_values = slot_values(assignment, "primary")
        auxiliary_values = slot_values(assignment, "auxiliary")
        primary = self._slot_view(primary_values, chat_rows, chain)
        auxiliary = self._slot_view(auxiliary_values, chat_rows, chain)
        has_primary = primary.row_id is not None or primary.model is not None
        has_auxiliary = auxiliary.row_id is not None or auxiliary.model is not None

        degraded_reason: str | None = None
        if not primary.pair_valid:
            degraded_reason = "no_active_provider"
        elif has_primary and not primary.usable:
            degraded_reason = "provider_inactive"
        if not auxiliary.pair_valid:
            degraded_reason = degraded_reason or "aux_no_active_provider"
        elif (
            has_auxiliary
            and not auxiliary.usable
            and degraded_reason is None
        ):
            degraded_reason = "provider_inactive"

        warnings: list[str] = []

        def warn(code: str) -> None:
            if code not in warnings:
                warnings.append(code)

        for view in (primary, auxiliary):
            if view.model is None:
                continue
            spec = spec_for(view.model)
            if spec is None:
                warn("unknown_model")
                continue
            if (
                view.provider != "none"
                and view.provider != "openai-compatible"
                and view.provider != spec.provider
            ):
                warn("provider_family_mismatch")
        primary_spec = spec_for(primary.model) if primary.model is not None else None
        if primary_spec is not None and assignment.context_window_tokens is not None:
            if assignment.context_window_tokens > primary_spec.context_window_tokens:
                warn("window_above_catalog")
            threshold = primary_spec.long_prompt_threshold_tokens
            if threshold is not None and assignment.context_window_tokens > threshold:
                warn("long_prompt_step")
        if auxiliary_values.inherited and has_primary:
            warn("aux_inherited_from_primary")

        return ModelAssignmentSchema(
            user_id=assignment.user_id,
            username=username,
            chat_provider_config_id=assignment.provider_config_id,
            chat_model=assignment.model,
            chat_reasoning_effort=assignment.reasoning_effort,
            aux_provider_config_id=assignment.aux_provider_config_id,
            aux_model=assignment.aux_model,
            aux_reasoning_effort=assignment.aux_reasoning_effort,
            chat_context_window_tokens=assignment.context_window_tokens,
            chat_compaction_threshold_tokens=assignment.compaction_threshold_tokens,
            chat_provider_label=primary.label,
            aux_provider_label=auxiliary.label,
            effective_chat_model=primary.model,
            effective_chat_provider=primary.provider,
            effective_chat_effort=primary.effort,
            effective_aux_model=auxiliary.model,
            effective_aux_provider=auxiliary.provider,
            effective_aux_effort=auxiliary.effort,
            effective_context_window_tokens=assignment.context_window_tokens,
            effective_compaction_threshold_tokens=(
                assignment.compaction_threshold_tokens
            ),
            chat_tier=primary.tier,
            aux_tier=auxiliary.tier,
            chat_pricing=primary.pricing,
            aux_pricing=auxiliary.pricing,
            source="account" if has_primary or has_auxiliary else "unassigned",
            degraded_reason=degraded_reason,
            warnings=warnings,
            updated_at=updated_at,
        )

    @staticmethod
    def _slot_view(
        values: SlotValues,
        chat_rows: dict[int, ChatProviderConfigModel],
        chain: dict[int, ProviderConfig],
    ) -> "_SlotView":
        row = chat_rows.get(values.row_id) if values.row_id is not None else None
        config = chain.get(values.row_id) if values.row_id is not None else None
        provider = (
            row.provider
            if row is not None
            else (config.provider if config is not None else "none")
        )
        label = (row.label or row.provider) if row is not None else None
        spec = spec_for(values.model) if values.model is not None else None
        usable = (
            config is not None
            and config.enabled
            and config.provider != "none"
            and bool(config.api_key)
        )
        return _SlotView(
            row_id=values.row_id,
            model=values.model,
            effort=values.effort,
            provider=provider,
            label=label,
            tier=spec.tier if spec is not None else None,
            pricing=ModelAssignmentService._pricing(
                spec.prices if spec is not None else None
            ),
            usable=usable,
            pair_valid=(values.row_id is None) == (values.model is None),
        )

    @staticmethod
    def _pricing(prices: ModelPrices | None) -> ModelPricingSchema | None:
        if prices is None:
            return None
        return ModelPricingSchema(
            input=float(prices.input),
            output=float(prices.output),
            cache_write=float(prices.cache_write),
            cache_read=float(prices.cache_read),
        )

    def _chain_index(self) -> dict[int, ProviderConfig]:
        return {
            config.row_id: config
            for config in self.runtime.chat_chain
            if config.row_id is not None
        }

    # ------------------------------------------------------------------
    # Small builders
    # ------------------------------------------------------------------

    @staticmethod
    def _assignment_from_account_model(account: AppUserModel) -> ChatAssignment:
        return ChatAssignment(
            user_id=account.id,
            provider_config_id=account.chat_provider_config_id,
            model=account.chat_model,
            reasoning_effort=account.chat_reasoning_effort,
            aux_provider_config_id=account.aux_provider_config_id,
            aux_model=account.aux_model,
            aux_reasoning_effort=(
                account.aux_reasoning_effort or DEFAULT_AUXILIARY_EFFORT
            ),
            context_window_tokens=account.chat_context_window_tokens,
            compaction_threshold_tokens=account.chat_compaction_threshold_tokens,
        )

    @staticmethod
    def _assignment_from_account_row(row: AccountAssignment) -> ChatAssignment:
        return ChatAssignment(
            user_id=row.user_id,
            provider_config_id=row.chat_provider_config_id,
            model=row.chat_model,
            reasoning_effort=row.chat_reasoning_effort,
            aux_provider_config_id=row.aux_provider_config_id,
            aux_model=row.aux_model,
            aux_reasoning_effort=(
                row.aux_reasoning_effort or DEFAULT_AUXILIARY_EFFORT
            ),
            context_window_tokens=row.chat_context_window_tokens,
            compaction_threshold_tokens=row.chat_compaction_threshold_tokens,
        )

    @staticmethod
    def _base_url_host(row: ChatProviderConfigModel) -> str | None:
        if row.provider == "none":
            return None
        base_url = row.base_url or default_base_url_for(CHAT_TABLE_SPEC, row.provider)
        if not base_url:
            return None
        return urlsplit(base_url).hostname

    @staticmethod
    def _probe_failure(detail: str) -> ChatEndpointProbeResultSchema:
        return ChatEndpointProbeResultSchema(
            ok=False,
            latency_ms=0,
            resolved_model=None,
            usage={},
            detail=detail,
        )


@dataclass(frozen=True)
class _SlotView:
    """Resolved view of one slot for the read projection."""

    row_id: int | None
    model: str | None
    effort: str | None
    provider: str
    label: str | None
    tier: str | None
    pricing: ModelPricingSchema | None
    usable: bool
    pair_valid: bool


__all__ = ["ModelAssignmentService"]
