import logging

from pydantic import ValidationError

from ..clients.alerts_api import AlertsApiClient, AlertsApiError
from ..clients.claude_client import ClaudeClient, ClaudeClientError
from ..dead_letter import write_dead_letter
from ..schemas import Feedback, FeedbackCategory, FeedbackClassification, FeedbackIn, Message

logger = logging.getLogger("ai_layer.services.feedback_classifier")


class FeedbackClassificationError(Exception):
    pass


_SYSTEM_PROMPT = (
    "You classify a WhatsApp/SMS reply to a disaster-alert message into exactly one "
    "of these fixed categories:\n"
    "- helpful: the user found the alert useful/actionable.\n"
    "- not_helpful: the user found the alert useless or irrelevant.\n"
    "- incorrect_location: the alert's ward/corridor/segment was wrong for this user.\n"
    "- incorrect_timing: the timing/window in the alert was wrong.\n"
    "- unclear: the message text was confusing or hard to understand.\n"
    "- other: anything that doesn't fit the above.\n"
    "Respond ONLY via the required structured schema, with a category and a confidence "
    "score between 0.0 and 1.0 reflecting how certain you are."
)

_STRICT_REMINDER = (
    "\n\nIMPORTANT: you MUST pick exactly one of: helpful, not_helpful, "
    "incorrect_location, incorrect_timing, unclear, other -- do not invent a new "
    "category. confidence MUST be a plain number between 0.0 and 1.0."
)

_FALLBACK_CLASSIFICATION = FeedbackClassification(category=FeedbackCategory.OTHER, confidence=0.0)

_RETRYABLE = (ClaudeClientError, ValidationError)


async def _classify_with_retry(reply_text: str, claude_client: ClaudeClient) -> FeedbackClassification:
    try:
        return await claude_client.parse_structured(
            system=_SYSTEM_PROMPT, user_content=reply_text, output_model=FeedbackClassification,
        )
    except _RETRYABLE as exc:
        logger.warning(
            "Claude feedback classification failed on first attempt; retrying once with "
            "a stricter prompt. error=%s reply_text=%r", exc, reply_text,
        )
        try:
            return await claude_client.parse_structured(
                system=_SYSTEM_PROMPT + _STRICT_REMINDER, user_content=reply_text,
                output_model=FeedbackClassification,
            )
        except _RETRYABLE as exc2:
            logger.error(
                "Claude feedback classification failed on retry; FALLING BACK to "
                "category=OTHER confidence=0.0. error=%s reply_text=%r", exc2, reply_text,
            )
            return _FALLBACK_CLASSIFICATION


async def classify_feedback(
    message: Message,
    reply_text: str,
    *,
    claude_client: ClaudeClient | None = None,
    alerts_api_client: AlertsApiClient | None = None,
) -> Feedback:
    claude_client = claude_client or ClaudeClient()
    classification = await _classify_with_retry(reply_text, claude_client)

    feedback_in = FeedbackIn(
        message_id=message.id,
        profile_id=message.profile_id,
        feedback_type=classification.category,
        feedback_text=reply_text,
    )
    feedback = await _post_feedback_with_dead_letter(feedback_in, alerts_api_client)
    feedback.confidence = classification.confidence
    feedback.classification_failed = classification is _FALLBACK_CLASSIFICATION
    return feedback


async def _post_feedback_with_dead_letter(feedback_in: FeedbackIn, client: AlertsApiClient | None) -> Feedback:
    client = client or AlertsApiClient()
    try:
        return await client.create_feedback(feedback_in)
    except AlertsApiError as exc:
        logger.error(
            "Failed to POST /feedback/ (message_id=%s profile_id=%s); writing dead-letter "
            "so it can be retried manually. error=%s",
            feedback_in.message_id, feedback_in.profile_id, exc,
        )
        write_dead_letter("feedback", feedback_in.model_dump(mode="json"))
        raise FeedbackClassificationError(f"failed to persist feedback: {exc}") from exc
