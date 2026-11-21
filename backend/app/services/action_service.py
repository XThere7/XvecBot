"""
services/action_service.py
Agent Actions: the single configuration surface for the capabilities an agent
can perform during a conversation.

An *action* is a tenant-scoped row in ``agent_actions``. The catalogue below is
the product-level definition (what the action does, which plan feature unlocks
it and which fields it collects by default); the row stores the owner's
configuration. Keeping one table means Lead Capture, Data Collection, Custom
Forms and Support escalation cannot drift into separate frameworks.

The LLM asks the backend to perform an action by emitting a directive:

    <botbase_action>{"type": "lead_capture", "data": {...}}</botbase_action>

Directives are parsed server-side, validated against the owner-defined field
schema, executed, and stripped from the answer the visitor sees. The model can
also ask for an interactive form:

    <botbase_action>{"type": "lead_capture", "mode": "request_form"}</botbase_action>

The API then returns a form payload that the dashboard chat renders. A visitor
can never inject arbitrary columns: only fields defined by the owner are read.
"""
from __future__ import annotations

import hashlib
import json
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite
from fastapi import HTTPException, status

from ..core.logging import get_logger
from ..core.plans import Plan
from ..models.engagement import (
    AgentActionCreate,
    AgentActionUpdate,
    ActionCatalogEntry,
    AgentActionsResponse,
)
from . import plan_service
from .field_schema import normalise_fields, validate_submission

log = get_logger(__name__)

ACTION_TYPES = (
    "lead_capture",
    "data_collection",
    "custom_forms",
    "knowledge_support",
)

MAX_DIRECTIVES_PER_TURN = 3

# Default lead fields. Owners can edit them; the canonical columns
# (full_name/email/phone/...) are filled from keys with the same name.
DEFAULT_LEAD_FIELDS: list[dict[str, Any]] = [
    {"key": "full_name", "label": "Full name", "type": "short_text", "required": True},
    {"key": "email", "label": "Email", "type": "email", "required": True},
    {"key": "phone", "label": "Phone", "type": "phone", "required": False},
    {"key": "company", "label": "Company", "type": "short_text", "required": False},
    {"key": "interest", "label": "What are you interested in?", "type": "long_text", "required": False},
    {"key": "budget", "label": "Budget", "type": "short_text", "required": False},
    {"key": "notes", "label": "Anything else we should know?", "type": "long_text", "required": False},
]

LEAD_COLUMNS = ("full_name", "email", "phone", "company", "interest", "budget", "notes")

_CONSENT_TEXT = (
    "I agree to be contacted about my enquiry and understand my details will "
    "be stored by this business."
)

# Product catalogue. `required_feature` is resolved against PlanFeatures.
ACTION_CATALOG: dict[str, dict[str, Any]] = {
    "lead_capture": {
        "category": "Sales & Lead Generation",
        "name": "Lead Capture",
        "description": (
            "Collect a visitor's contact details and sales interest, store them "
            "as a lead, and let the team follow up."
        ),
        "required_feature": "actions",
        "default_config": {
            "fields": DEFAULT_LEAD_FIELDS,
            "require_consent": True,
            "consent_text": _CONSENT_TEXT,
            "notify_email": None,
        },
    },
    "data_collection": {
        "category": "Sales & Lead Generation",
        "name": "Data Collection",
        "description": (
            "Ask structured questions and store each answer set as a submission "
            "that can be reviewed or exported."
        ),
        "required_feature": "actions",
        "default_config": {
            "fields": [
                {"key": "full_name", "label": "Full name", "type": "short_text", "required": True},
                {"key": "email", "label": "Email", "type": "email", "required": True},
                {"key": "feedback", "label": "Your feedback", "type": "long_text", "required": False},
            ],
            "require_consent": False,
            "collection_id": None,
        },
    },
    "custom_forms": {
        "category": "Customer Engagement",
        "name": "Custom Forms",
        "description": (
            "Publish a shareable form with a public link. Submissions are stored "
            "against the agent and can be reviewed in the dashboard."
        ),
        "required_feature": "actions",
        "default_config": {
            "form_id": None,
            "require_consent": True,
        },
    },
    "knowledge_support": {
        "category": "Customer Support",
        "name": "Support Escalation",
        "description": (
            "Recognise when a question needs a human and create an escalation "
            "with the visitor's contact details."
        ),
        "required_feature": "always",
        "default_config": {
            "notify_email": None,
            "reason_template": "Customer requested human support",
        },
    },
}

_DIRECTIVE_RE = re.compile(
    r"<botbase_action>\s*(\{.*?\})\s*</botbase_action>",
    re.DOTALL | re.IGNORECASE,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_load(raw: Any, default: Any) -> Any:
    if not raw:
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _row_to_action(row: Any) -> dict[str, Any]:
    data = dict(row)
    data["config"] = _json_load(data.get("config"), {})
    return data


def _catalog_entry(action_type: str) -> dict[str, Any]:
    return ACTION_CATALOG[action_type]


def _locked_reason(feature: str) -> str:
    return (
        f"{feature.replace('_', ' ').capitalize()} is included in Standard and "
        "Pro. Upgrade this workspace to enable it."
    )


async def _require_feature_for_actions(db: aiosqlite.Connection, workspace: dict) -> None:
    """Gate Data Collection / Custom Forms creation on the `actions` feature."""
    plan = await plan_service.plan_for_workspace(db, workspace)
    if not plan_service.feature_enabled(plan, "actions"):
        raise plan_service.limit_error(
            resource="actions",
            plan=plan,
            used=0,
            limit=0,
            code="plan_feature_locked",
            message=_locked_reason("actions"),
        )


def _clean_config(action_type: str, config: Optional[dict[str, Any]]) -> dict[str, Any]:
    """Validate owner-supplied configuration and merge it with the defaults."""
    base = json.loads(json.dumps(_catalog_entry(action_type)["default_config"]))
    incoming = config or {}
    if not isinstance(incoming, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Action configuration must be an object.",
        )

    merged = {**base, **incoming}
    if "fields" in incoming or action_type in ("lead_capture", "data_collection"):
        try:
            merged["fields"] = normalise_fields(
                incoming.get("fields", base.get("fields", []))
            )
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            )
    if "require_consent" in merged:
        merged["require_consent"] = bool(merged["require_consent"])
    for key in ("consent_text", "notify_email", "reason_template"):
        if key in merged and merged[key] is not None:
            merged[key] = str(merged[key])[:1000]
    return merged


async def _require_agent(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str
) -> dict:
    async with db.execute(
        "SELECT * FROM agents WHERE id = ? AND workspace_id = ?",
        (agent_id, workspace_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Agent not found"
        )
    return dict(row)


async def get_action(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    action_type: str,
) -> Optional[dict]:
    async with db.execute(
        """SELECT * FROM agent_actions
           WHERE workspace_id = ? AND agent_id = ? AND action_type = ?""",
        (workspace_id, agent_id, action_type),
    ) as cur:
        row = await cur.fetchone()
    return _row_to_action(row) if row is not None else None


async def list_actions(
    db: aiosqlite.Connection, workspace_id: str, agent_id: str
) -> list[dict]:
    async with db.execute(
        """SELECT * FROM agent_actions
           WHERE workspace_id = ? AND agent_id = ?
           ORDER BY created_at ASC""",
        (workspace_id, agent_id),
    ) as cur:
        rows = await cur.fetchall()
    return [_row_to_action(r) for r in rows]


async def catalog_for_agent(
    db: aiosqlite.Connection, workspace: dict, agent_id: str
) -> AgentActionsResponse:
    """Return every catalogue action with plan availability + the saved row."""
    await _require_agent(db, workspace["id"], agent_id)
    plan = await plan_service.plan_for_workspace(db, workspace)
    existing = {a["action_type"]: a for a in await list_actions(db, workspace["id"], agent_id)}

    entries: list[ActionCatalogEntry] = []
    for action_type in ACTION_TYPES:
        meta = _catalog_entry(action_type)
        feature = meta["required_feature"]
        available = plan_service.feature_enabled(plan, feature)
        entries.append(
            ActionCatalogEntry(
                action_type=action_type,
                category=meta["category"],
                name=meta["name"],
                description=meta["description"],
                required_feature=feature,
                plan_available=available,
                locked_reason=None if available else _locked_reason(feature),
                default_config=meta["default_config"],
                action=existing.get(action_type),
            )
        )
    return AgentActionsResponse(
        catalog=entries,
        plan_features={k: bool(v) for k, v in plan.features.items() if isinstance(v, bool)},
    )


async def upsert_action(
    db: aiosqlite.Connection,
    workspace: dict,
    agent_id: str,
    payload: AgentActionCreate | AgentActionUpdate,
    *,
    action_type: Optional[str] = None,
) -> dict:
    """Create or update one action. Enforces the plan feature on write."""
    await _require_agent(db, workspace["id"], agent_id)
    resolved_type = action_type or getattr(payload, "action_type", None)
    if resolved_type not in ACTION_CATALOG:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unknown action type.",
        )

    meta = _catalog_entry(resolved_type)
    plan = await plan_service.plan_for_workspace(db, workspace)
    if not plan_service.feature_enabled(plan, meta["required_feature"]):
        raise plan_service.limit_error(
            resource=meta["required_feature"],
            plan=plan,
            used=0,
            limit=0,
            code="plan_feature_locked",
            message=_locked_reason(meta["required_feature"]),
        )

    existing = await get_action(db, workspace["id"], agent_id, resolved_type)
    now = _now()
    config = _clean_config(
        resolved_type,
        getattr(payload, "config", None)
        if getattr(payload, "config", None) is not None
        else (existing["config"] if existing else None),
    )
    name = (getattr(payload, "name", None) or (existing or {}).get("name") or meta["name"]).strip()[:120]
    description = getattr(payload, "description", None)
    if description is None and existing:
        description = existing.get("description")
    description = (description or meta["description"]).strip()[:1000]
    instructions = getattr(payload, "instructions", None)
    if instructions is None and existing:
        instructions = existing.get("instructions")
    instructions = (instructions or "").strip()[:4000] or None
    is_active = getattr(payload, "is_active", None)
    if is_active is None:
        is_active = bool((existing or {}).get("is_active", 1))

    if existing:
        await db.execute(
            """UPDATE agent_actions
               SET name = ?, description = ?, instructions = ?, is_active = ?,
                   config = ?, updated_at = ?
               WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
            (
                name,
                description,
                instructions,
                1 if is_active else 0,
                json.dumps(config),
                now,
                existing["id"],
                workspace["id"],
                agent_id,
            ),
        )
        action_id = existing["id"]
    else:
        action_id = str(uuid.uuid4())
        await db.execute(
            """INSERT INTO agent_actions
               (id, workspace_id, agent_id, action_type, name, description,
                instructions, is_active, config, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                action_id,
                workspace["id"],
                agent_id,
                resolved_type,
                name,
                description,
                instructions,
                1 if is_active else 0,
                json.dumps(config),
                now,
                now,
            ),
        )
    await db.commit()
    saved = await get_action(db, workspace["id"], agent_id, resolved_type)
    assert saved is not None
    log.info(
        "Agent action saved",
        workspace_id=workspace["id"],
        agent_id=agent_id,
        action_type=resolved_type,
        action_id=action_id,
        is_active=bool(is_active),
    )
    return saved


async def delete_action(
    db: aiosqlite.Connection,
    workspace_id: str,
    agent_id: str,
    action_type: str,
) -> None:
    await db.execute(
        """DELETE FROM agent_actions
           WHERE workspace_id = ? AND agent_id = ? AND action_type = ?""",
        (workspace_id, agent_id, action_type),
    )
    await db.commit()


async def seed_default_actions(
    db: aiosqlite.Connection,
    workspace: dict,
    agent_id: str,
    action_types: Optional[list[str]] = None,
) -> list[dict]:
    """Create the requested actions (or every plan-allowed action) for a new agent."""
    plan = await plan_service.plan_for_workspace(db, workspace)
    requested = action_types if action_types is not None else list(ACTION_TYPES)
    created: list[dict] = []
    for action_type in requested:
        if action_type not in ACTION_CATALOG:
            continue
        meta = _catalog_entry(action_type)
        if not plan_service.feature_enabled(plan, meta["required_feature"]):
            continue
        if await get_action(db, workspace["id"], agent_id, action_type):
            continue
        created.append(
            await upsert_action(
                db,
                workspace,
                agent_id,
                AgentActionCreate(action_type=action_type),
            )
        )
    return created


def build_action_prompt(actions: list[dict]) -> str:
    """Describe active actions + the directive protocol to the model."""
    active = [a for a in actions if a.get("is_active")]
    if not active:
        return ""
    lines = [
        "You can perform actions for this business. Only use an action when the",
        "visitor clearly asks for it or provides the information it needs.",
        "To request an interactive form, reply with:",
        '<botbase_action>{"type":"ACTION_TYPE","mode":"request_form"}</botbase_action>',
        "To perform an action with information the visitor already provided, reply with:",
        '<botbase_action>{"type":"ACTION_TYPE","data":{"field":"value"}}</botbase_action>',
        "Never invent values. Never include more than one directive per action.",
        "The directive is removed before the visitor sees your reply, so keep the",
        "rest of the answer natural and helpful.",
        "",
        "Available actions:",
    ]
    for action in active:
        config = action.get("config") or {}
        lines.append(f"- {action['action_type']}: {action.get('description') or ''}")
        if action["action_type"] in ("lead_capture", "data_collection"):
            fields = config.get("fields") or []
            names = ", ".join(
                f"{f.get('key')} ({f.get('type')}{', required' if f.get('required') else ''})"
                for f in fields
            )
            if names:
                lines.append(f"  Fields: {names}")
        if action["action_type"] == "knowledge_support":
            lines.append(
                '  Use data {"reason": "...", "contact_name": "...", '
                '"contact_email": "..."} when a human is needed.'
            )
    return "\n".join(lines)


def parse_directives(answer: str) -> tuple[str, list[dict[str, Any]]]:
    """Strip directives from the model answer and return parsed payloads."""
    directives: list[dict[str, Any]] = []
    for match in _DIRECTIVE_RE.finditer(answer or ""):
        try:
            payload = json.loads(match.group(1))
        except (TypeError, ValueError):
            log.warning("Ignoring malformed action directive")
            continue
        if isinstance(payload, dict) and payload.get("type") in ACTION_CATALOG:
            directives.append(payload)
        if len(directives) >= MAX_DIRECTIVES_PER_TURN:
            break
    cleaned = _DIRECTIVE_RE.sub("", answer or "").strip()
    return cleaned, directives


def strip_directive_markup(text: str) -> str:
    """Remove action-control markup from untrusted visitor input.

    The model is the only component allowed to produce directives. If the raw
    visitor text contains the tags (prompt-injection attempt or copy/paste), the
    tags are removed before the message is stored or sent to the model, so they
    cannot be echoed back and executed.
    """
    cleaned = _DIRECTIVE_RE.sub("", text or "").strip()
    return cleaned or "(message contained only unsupported control markup)"


def _form_payload(
    action: dict[str, Any],
    *,
    title: str,
    description: str,
    fields: list[dict[str, Any]],
    require_consent: bool,
    consent_text: Optional[str] = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "kind": "action_form",
        "action_id": action["id"],
        "action_type": action["action_type"],
        "title": title,
        "description": description,
        "fields": fields,
        "require_consent": require_consent,
        "submit_label": "Submit",
    }
    if consent_text:
        payload["consent_text"] = consent_text
    return payload


async def _execute_lead_capture(
    db: aiosqlite.Connection,
    workspace: dict,
    agent_id: str,
    action: dict[str, Any],
    directive: dict[str, Any],
    conversation_id: Optional[str],
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    from . import lead_service

    config = action.get("config") or {}
    fields = config.get("fields") or DEFAULT_LEAD_FIELDS
    require_consent = bool(config.get("require_consent", True))
    consent_text = config.get("consent_text")

    if directive.get("mode") == "request_form":
        return (
            {
                "type": "form_requested",
                "action_type": "lead_capture",
                "label": "Lead capture form ready",
            },
            _form_payload(
                action,
                title="Share your details",
                description="Tell us how to reach you and what you need.",
                fields=fields,
                require_consent=require_consent,
                consent_text=consent_text,
            ),
        )

    raw_data = directive.get("data") or {}
    consent = bool(raw_data.get("_consent")) if require_consent else False
    if require_consent and not consent:
        # Never persist contact details without consent. Ask for the form so the
        # visitor can tick the consent box explicitly.
        return (
            {
                "type": "form_requested",
                "action_type": "lead_capture",
                "label": "Lead capture form ready",
            },
            _form_payload(
                action,
                title="Share your details",
                description="Tell us how to reach you and what you need.",
                fields=fields,
                require_consent=True,
                consent_text=consent_text,
            ),
        )

    cleaned, missing, errors = validate_submission(
        fields,
        raw_data,
        allow_partial=True,
        require_consent=False,
    )
    if errors:
        return (
            {
                "type": "validation_error",
                "action_type": "lead_capture",
                "label": "Some lead details need attention",
                "errors": errors,
            },
            None,
        )
    if not cleaned:
        return (
            {
                "type": "form_requested",
                "action_type": "lead_capture",
                "label": "Lead capture form ready",
            },
            _form_payload(
                action,
                title="Share your details",
                description="Tell us how to reach you and what you need.",
                fields=fields,
                require_consent=require_consent,
                consent_text=consent_text,
            ),
        )

    lead = await lead_service.upsert_lead(
        db,
        workspace=workspace,
        agent_id=agent_id,
        action_id=action["id"],
        conversation_id=conversation_id,
        data=cleaned,
        status="partial" if missing else "complete",
        consent_given=consent,
        consent_text=consent_text if require_consent else None,
    )
    return (
        {
            "type": "lead_saved",
            "action_type": "lead_capture",
            "label": "Lead captured",
            "id": lead["id"],
            "status": lead["status"],
        },
        None,
    )


async def _execute_data_collection(
    db: aiosqlite.Connection,
    workspace: dict,
    agent_id: str,
    action: dict[str, Any],
    directive: dict[str, Any],
    conversation_id: Optional[str],
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    from . import capture_service

    config = action.get("config") or {}
    collection = None
    if config.get("collection_id"):
        collection = await capture_service.get_collection(
            db, workspace["id"], agent_id, config["collection_id"]
        )
    if collection is None:
        collections = await capture_service.list_collections(
            db, workspace["id"], agent_id, active_only=True
        )
        collection = collections[0] if collections else None
    if collection is None:
        # No collection configured yet: use the action's inline fields.
        fields = config.get("fields") or []
        if directive.get("mode") == "request_form":
            return (
                {
                    "type": "form_requested",
                    "action_type": "data_collection",
                    "label": "Data collection form ready",
                },
                _form_payload(
                    action,
                    title="Tell us more",
                    description="Answer a few quick questions.",
                    fields=fields,
                    require_consent=bool(config.get("require_consent")),
                ),
            )
        cleaned, missing, errors = validate_submission(
            fields, directive.get("data") or {}, allow_partial=True
        )
        if errors or not cleaned:
            return (
                {
                    "type": "validation_error",
                    "action_type": "data_collection",
                    "label": "Data could not be saved",
                    "errors": errors or ["No information was provided."],
                },
                None,
            )
        submission = await capture_service.create_submission(
            db,
            workspace=workspace,
            agent_id=agent_id,
            collection_id=None,
            conversation_id=conversation_id,
            data=cleaned,
            status="partial" if missing else "complete",
            inline_fields=fields,
        )
        return (
            {
                "type": "data_saved",
                "action_type": "data_collection",
                "label": "Information saved",
                "id": submission["id"],
            },
            None,
        )

    if directive.get("mode") == "request_form":
        return (
            {
                "type": "form_requested",
                "action_type": "data_collection",
                "label": "Data collection form ready",
            },
            _form_payload(
                action,
                title=collection["name"],
                description=collection.get("description") or "Answer a few quick questions.",
                fields=collection["fields"],
                require_consent=bool(collection.get("require_consent")),
            ),
        )

    cleaned, missing, errors = validate_submission(
        collection["fields"],
        directive.get("data") or {},
        allow_partial=bool(collection.get("allow_partial")),
        require_consent=bool(collection.get("require_consent")),
    )
    if errors:
        return (
            {
                "type": "validation_error",
                "action_type": "data_collection",
                "label": "Data could not be saved",
                "errors": errors,
            },
            None,
        )
    submission = await capture_service.create_submission(
        db,
        workspace=workspace,
        agent_id=agent_id,
        collection_id=collection["id"],
        conversation_id=conversation_id,
        data=cleaned,
        status="partial" if missing else "complete",
    )
    return (
        {
            "type": "data_saved",
            "action_type": "data_collection",
            "label": "Information saved",
            "id": submission["id"],
        },
        None,
    )


async def _execute_custom_form(
    db: aiosqlite.Connection,
    workspace: dict,
    agent_id: str,
    action: dict[str, Any],
    directive: dict[str, Any],
    conversation_id: Optional[str],
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    from . import capture_service

    config = action.get("config") or {}
    form = None
    if config.get("form_id"):
        form = await capture_service.get_form(db, workspace["id"], agent_id, config["form_id"])
    if form is None:
        forms = await capture_service.list_forms(db, workspace["id"], agent_id, active_only=True)
        form = forms[0] if forms else None
    if form is None:
        return (
            {
                "type": "validation_error",
                "action_type": "custom_forms",
                "label": "No form has been published yet",
                "errors": ["Create a form in the Custom Forms action first."],
            },
            None,
        )
    return (
        {
            "type": "form_requested",
            "action_type": "custom_forms",
            "label": "Form ready",
            "form_token": form["public_token"],
        },
        _form_payload(
            action,
            title=form["title"],
            description=form.get("description") or "",
            fields=form["fields"],
            require_consent=bool(form.get("require_consent")),
        ),
    )


async def _execute_support(
    db: aiosqlite.Connection,
    workspace: dict,
    agent_id: str,
    action: dict[str, Any],
    directive: dict[str, Any],
    conversation_id: Optional[str],
) -> tuple[dict[str, Any], Optional[dict[str, Any]]]:
    from . import support_service

    data = directive.get("data") or {}
    reason = str(data.get("reason") or (action.get("config") or {}).get("reason_template") or "").strip()
    if not reason:
        reason = "Customer requested human support"
    escalation = await support_service.create_escalation(
        db,
        workspace=workspace,
        agent_id=agent_id,
        conversation_id=conversation_id,
        reason=reason[:1000],
        contact_name=(str(data.get("contact_name") or "").strip() or None),
        contact_email=(str(data.get("contact_email") or "").strip() or None),
        contact_phone=(str(data.get("contact_phone") or "").strip() or None),
    )
    return (
        {
            "type": "support_escalated",
            "action_type": "knowledge_support",
            "label": "Support escalation created",
            "id": escalation["id"],
        },
        None,
    )


async def execute_directives(
    db: aiosqlite.Connection,
    workspace: dict,
    agent_id: str,
    directives: list[dict[str, Any]],
    conversation_id: Optional[str],
) -> tuple[list[dict[str, Any]], Optional[dict[str, Any]]]:
    """Run parsed directives; returns (results, first form payload)."""
    actions = {a["action_type"]: a for a in await list_actions(db, workspace["id"], agent_id)}
    results: list[dict[str, Any]] = []
    form: Optional[dict[str, Any]] = None
    plan = await plan_service.plan_for_workspace(db, workspace)

    handlers = {
        "lead_capture": _execute_lead_capture,
        "data_collection": _execute_data_collection,
        "custom_forms": _execute_custom_form,
        "knowledge_support": _execute_support,
    }
    for directive in directives:
        action_type = directive.get("type")
        action = actions.get(action_type)
        if action is None or not action.get("is_active"):
            results.append(
                {
                    "type": "unavailable",
                    "action_type": action_type,
                    "label": "That action is not enabled for this agent",
                }
            )
            continue
        if not plan_service.feature_enabled(
            plan, _catalog_entry(action_type)["required_feature"]
        ):
            results.append(
                {
                    "type": "unavailable",
                    "action_type": action_type,
                    "label": "That action is not included in the current plan",
                }
            )
            continue
        handler = handlers.get(action_type)
        if handler is None:
            continue
        try:
            result, requested_form = await handler(
                db, workspace, agent_id, action, directive, conversation_id
            )
        except HTTPException as exc:
            results.append(
                {
                    "type": "validation_error",
                    "action_type": action_type,
                    "label": str(exc.detail),
                    "errors": [str(exc.detail)],
                }
            )
            continue
        except Exception as exc:  # pragma: no cover - defensive
            log.warning(
                "Action directive failed",
                action_type=action_type,
                error=type(exc).__name__,
            )
            results.append(
                {
                    "type": "error",
                    "action_type": action_type,
                    "label": "The action could not be completed",
                }
            )
            continue
        results.append(result)
        if requested_form is not None and form is None:
            form = requested_form
    return results, form


async def submit_action_form(
    db: aiosqlite.Connection,
    workspace: dict,
    agent_id: str,
    action_id: str,
    data: dict[str, Any],
    conversation_id: Optional[str],
) -> dict[str, Any]:
    """Handle an interactive form submitted from the dashboard chat."""
    async with db.execute(
        """SELECT * FROM agent_actions
           WHERE id = ? AND workspace_id = ? AND agent_id = ?""",
        (action_id, workspace["id"], agent_id),
    ) as cur:
        row = await cur.fetchone()
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Action not found"
        )
    action = _row_to_action(row)
    if not action.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="This action is disabled.",
        )

    action_type = action["action_type"]
    meta = _catalog_entry(action_type)
    plan = await plan_service.plan_for_workspace(db, workspace)
    if not plan_service.feature_enabled(plan, meta["required_feature"]):
        raise plan_service.limit_error(
            resource=meta["required_feature"],
            plan=plan,
            used=0,
            limit=0,
            code="plan_feature_locked",
            message=_locked_reason(meta["required_feature"]),
        )
    config = action.get("config") or {}
    if action_type == "lead_capture":
        from . import lead_service

        fields = config.get("fields") or DEFAULT_LEAD_FIELDS
        require_consent = bool(config.get("require_consent", True))
        cleaned, missing, errors = validate_submission(
            fields, data, allow_partial=False, require_consent=require_consent
        )
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "Please check the form.", "errors": errors},
            )
        lead = await lead_service.upsert_lead(
            db,
            workspace=workspace,
            agent_id=agent_id,
            action_id=action["id"],
            conversation_id=conversation_id,
            data=cleaned,
            status="complete",
            consent_given=bool(require_consent),
            consent_text=config.get("consent_text") if require_consent else None,
        )
        return {"kind": "lead", "item": lead, "label": "Lead captured"}

    if action_type == "data_collection":
        from . import capture_service

        collection = None
        if config.get("collection_id"):
            collection = await capture_service.get_collection(
                db, workspace["id"], agent_id, config["collection_id"]
            )
        if collection is None:
            collections = await capture_service.list_collections(
                db, workspace["id"], agent_id, active_only=True
            )
            collection = collections[0] if collections else None
        if collection is None:
            fields = config.get("fields") or []
            cleaned, missing, errors = validate_submission(
                fields, data, allow_partial=False,
                require_consent=bool(config.get("require_consent")),
            )
            if errors:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail={"message": "Please check the form.", "errors": errors},
                )
            submission = await capture_service.create_submission(
                db,
                workspace=workspace,
                agent_id=agent_id,
                collection_id=None,
                conversation_id=conversation_id,
                data=cleaned,
                status="complete",
                inline_fields=fields,
            )
            return {"kind": "submission", "item": submission, "label": "Information saved"}
        cleaned, missing, errors = validate_submission(
            collection["fields"],
            data,
            allow_partial=False,
            require_consent=bool(collection.get("require_consent")),
        )
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "Please check the form.", "errors": errors},
            )
        submission = await capture_service.create_submission(
            db,
            workspace=workspace,
            agent_id=agent_id,
            collection_id=collection["id"],
            conversation_id=conversation_id,
            data=cleaned,
            status="complete",
        )
        return {"kind": "submission", "item": submission, "label": "Information saved"}

    if action_type == "custom_forms":
        from . import capture_service

        form = None
        if config.get("form_id"):
            form = await capture_service.get_form(
                db, workspace["id"], agent_id, config["form_id"]
            )
        if form is None:
            forms = await capture_service.list_forms(
                db, workspace["id"], agent_id, active_only=True
            )
            form = forms[0] if forms else None
        if form is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="No form has been published yet.",
            )
        cleaned, missing, errors = validate_submission(
            form["fields"],
            data,
            allow_partial=False,
            require_consent=bool(form.get("require_consent")),
        )
        if errors:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={"message": "Please check the form.", "errors": errors},
            )
        submission = await capture_service.submit_public_form(
            db, form["public_token"], data
        )
        return {"kind": "form_submission", "item": submission, "label": "Form submitted"}

    if action_type == "knowledge_support":
        from . import support_service

        escalation = await support_service.create_escalation(
            db,
            workspace=workspace,
            agent_id=agent_id,
            conversation_id=conversation_id,
            reason=str(data.get("reason") or "Customer requested human support")[:1000],
            contact_name=(str(data.get("contact_name") or "").strip() or None),
            contact_email=(str(data.get("contact_email") or "").strip() or None),
            contact_phone=(str(data.get("contact_phone") or "").strip() or None),
        )
        return {"kind": "escalation", "item": escalation, "label": "Support escalation created"}

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="This action does not accept a form submission.",
    )


def dedupe_key_for(data: dict[str, Any], conversation_id: Optional[str]) -> str:
    """Stable identity for a lead: email, then phone, then name/company/thread."""
    email = str(data.get("email") or "").strip().lower()
    if email:
        return f"email:{email}"
    phone = re.sub(r"\D", "", str(data.get("phone") or ""))
    if phone:
        return f"phone:{phone}"
    basis = "|".join(
        [
            str(data.get("full_name") or "").strip().lower(),
            str(data.get("company") or "").strip().lower(),
            conversation_id or "",
        ]
    )
    return "hash:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()
