import logging
import re

from pydantic import BaseModel, ValidationError

from ..clients.alerts_api import AlertsApiClient, AlertsApiError
from ..clients.claude_client import ClaudeClient, ClaudeClientError
from ..dead_letter import write_dead_letter
from ..schemas import Alert, Profile, TemplateMatch, PredictionMatch, MessageIn, Message

logger = logging.getLogger("ai_layer.services.personalizer")

_KNOWN_TOKEN = re.compile(r"\{(\w+)\}")   # tokens we know how to fill
_ANY_BRACE = re.compile(r"\{[^{}]*\}")     # post-substitution safety net: ANY remaining brace pair


class PersonalizationError(Exception):
    pass


class MissingPlaceholderValueError(PersonalizationError):
    def __init__(self, placeholder_name: str):
        super().__init__(f"no value available for placeholder {{{placeholder_name}}}")
        self.placeholder_name = placeholder_name


class LeftoverPlaceholderError(PersonalizationError):
    def __init__(self, leftover_text: str):
        super().__init__(f"unfilled placeholder-like token remained after substitution: {leftover_text!r}")
        self.leftover_text = leftover_text


class InvalidClaudeResponseError(PersonalizationError):
    pass


class MessageDeliveryError(PersonalizationError):
    pass


class FloodWarningDraft(BaseModel):
    message_text: str


def build_placeholder_values(alert: Alert, profile: Profile) -> dict[str, str]:
    """Maps every placeholder relevant to the TemplateMatch (ward-track) path, per
    API_GUIDE.md's placeholder table, to a real typed value. Only includes a key when
    the underlying source data is actually present and correctly typed -- fill_placeholders
    is what raises MissingPlaceholderValueError when a template references a key that
    isn't here."""
    values: dict[str, str] = {"rainfall_mm": str(alert.rainfall_mm)}
    if alert.geography_type == "ward":
        values["ward"] = alert.geography_ref
    elif alert.geography_type == "corridor":
        values["corridor"] = alert.geography_ref
    if profile.occupation:
        values["occupation"] = profile.occupation
    if profile.key_asset:
        values["key_asset"] = profile.key_asset
    if profile.route_id:
        values["route_id"] = profile.route_id
    return values


def fill_placeholders(template_text: str, values: dict[str, str]) -> str:
    """Substitutes every {token} in template_text using values. Raises
    MissingPlaceholderValueError for any KNOWN-shape token ({word}) with no entry in
    values. After substitution, defensively re-scans for ANY remaining {...} --
    including malformed tokens the pre-check regex wouldn't even recognize (e.g. a stray
    "{when?}") -- and raises LeftoverPlaceholderError. A leftover placeholder must never
    reach a user."""
    for match in _KNOWN_TOKEN.finditer(template_text):
        name = match.group(1)
        if name not in values:
            raise MissingPlaceholderValueError(name)

    filled = _KNOWN_TOKEN.sub(lambda m: values[m.group(1)], template_text)

    leftover = _ANY_BRACE.search(filled)
    if leftover:
        raise LeftoverPlaceholderError(leftover.group(0))

    return filled


_GRAMMAR_SYSTEM_PROMPT = (
    "You are a careful copy-editor for safety-critical disaster-alert SMS/WhatsApp "
    "messages sent to farmers, fishermen, and drivers. Fix ONLY grammar, spelling, and "
    "awkward phrasing. Do NOT change, add, or remove any factual value: numbers, place "
    "names, dates, times, or risk levels must stay byte-for-byte identical. Do NOT add "
    "new instructions or omit existing ones. Reply with ONLY the corrected message text "
    "-- no preamble, no quotes, no explanation."
)


async def _apply_grammar_pass(filled_text: str, claude_client: ClaudeClient) -> str:
    try:
        corrected = (
            await claude_client.create_text(
                system=_GRAMMAR_SYSTEM_PROMPT, user_content=filled_text, max_tokens=512,
            )
        ).strip()
        if not corrected:
            raise InvalidClaudeResponseError("empty response from grammar pass")
        return corrected
    except (ClaudeClientError, InvalidClaudeResponseError) as exc:
        logger.error(
            "Claude grammar pass failed/invalid; FALLING BACK to unedited template text. "
            "error=%s filled_text=%r", exc, filled_text,
        )
        return filled_text


_FLOOD_SYSTEM_PROMPT = (
    "You write short, clear flood-risk warning SMS messages for drivers, from structured "
    "input fields. Respond ONLY via the required structured schema. Your message_text must "
    "mention the segment name and the risk level; if a time window is given, mention it too. "
    "Do not invent any data not present in the input."
)


async def _build_flood_warning_text(content: PredictionMatch, claude_client: ClaudeClient) -> str:
    user_content = (
        f"segment_name={content.segment_name}\nrisk_level={content.risk_level}\n"
        f"window_start={content.window_start}\nwindow_end={content.window_end}\n"
        f"route_id={content.profile.route_id}\nlanguage={content.profile.language}"
    )
    try:
        draft = await claude_client.parse_structured(
            system=_FLOOD_SYSTEM_PROMPT, user_content=user_content,
            output_model=FloodWarningDraft, max_tokens=512,
        )
        text = draft.message_text.strip()
        if not text:
            raise InvalidClaudeResponseError("empty message_text")
        return text
    except (ClaudeClientError, ValidationError, InvalidClaudeResponseError) as exc:
        logger.error(
            "Claude flood-warning generation failed/invalid; FALLING BACK to plain "
            "structured-field sentence. error=%s segment=%s risk=%s",
            exc, content.segment_name, content.risk_level,
        )
        return _plain_flood_sentence(content)


def _plain_flood_sentence(content: PredictionMatch) -> str:
    window_phrase = ""
    if content.window_start and content.window_end:
        window_phrase = f" between {content.window_start.isoformat()} and {content.window_end.isoformat()}"
    return (
        f"Flood risk alert: {content.risk_level} risk of flooding on "
        f"{content.segment_name}{window_phrase}. Please take precaution."
    )


async def personalize_message(
    alert: Alert,
    profile: Profile,
    content: TemplateMatch | PredictionMatch,
    *,
    claude_client: ClaudeClient | None = None,
    alerts_api_client: AlertsApiClient | None = None,
) -> Message:
    claude_client = claude_client or ClaudeClient()

    if isinstance(content, TemplateMatch):
        values = build_placeholder_values(alert, profile)
        filled = fill_placeholders(content.template.template_text, values)
        final_text = await _apply_grammar_pass(filled, claude_client)
        template_id, flood_prediction_id = content.template.id, None
    elif isinstance(content, PredictionMatch):
        final_text = await _build_flood_warning_text(content, claude_client)
        template_id, flood_prediction_id = None, content.flood_prediction_id
    else:
        raise TypeError(f"personalize_message expects TemplateMatch or PredictionMatch, got {type(content)}")

    message_in = MessageIn(
        profile_id=profile.id,
        alert_id=alert.id,
        template_id=template_id,
        flood_prediction_id=flood_prediction_id,
        final_text=final_text,
        channel=profile.channel,
    )
    return await _post_message_with_dead_letter(message_in, alerts_api_client)


async def _post_message_with_dead_letter(message_in: MessageIn, client: AlertsApiClient | None) -> Message:
    client = client or AlertsApiClient()
    try:
        return await client.create_message(message_in)
    except AlertsApiError as exc:
        logger.error(
            "Failed to POST /messages/ (profile_id=%s alert_id=%s); "
            "writing dead-letter so it can be retried manually. error=%s",
            message_in.profile_id, message_in.alert_id, exc,
        )
        write_dead_letter("message", message_in.model_dump(mode="json"))
        raise MessageDeliveryError(f"failed to persist message: {exc}") from exc
