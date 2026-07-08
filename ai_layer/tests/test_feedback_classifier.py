import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from ai_layer.clients.claude_client import ClaudeClientError
from ai_layer.schemas import Feedback, FeedbackCategory, FeedbackClassification
from ai_layer.services.feedback_classifier import classify_feedback


async def test_classify_feedback_happy_path(sample_message):
    mock_claude = AsyncMock()
    mock_claude.parse_structured = AsyncMock(
        return_value=FeedbackClassification(category=FeedbackCategory.HELPFUL, confidence=0.9)
    )

    mock_api = AsyncMock()
    mock_api.create_feedback = AsyncMock(
        return_value=Feedback(
            id=42, message_id=sample_message.id, profile_id=sample_message.profile_id,
            feedback_type=FeedbackCategory.HELPFUL, feedback_text="thanks, very useful",
            created_at=datetime.now(timezone.utc),
        )
    )

    result = await classify_feedback(
        sample_message, "thanks, very useful", claude_client=mock_claude, alerts_api_client=mock_api,
    )

    assert result.id == 42
    assert result.feedback_type == FeedbackCategory.HELPFUL
    assert result.confidence == 0.9
    assert result.classification_failed is False
    mock_claude.parse_structured.assert_awaited_once()
    mock_api.create_feedback.assert_awaited_once()
    posted = mock_api.create_feedback.await_args.args[0]
    assert posted.message_id == sample_message.id
    assert posted.profile_id == sample_message.profile_id
    assert posted.feedback_type == FeedbackCategory.HELPFUL
    assert posted.feedback_text == "thanks, very useful"


async def test_classify_feedback_malformed_then_fallback_to_other(sample_message, caplog):
    mock_claude = AsyncMock()
    mock_claude.parse_structured = AsyncMock(
        side_effect=[ClaudeClientError("malformed response 1"), ClaudeClientError("malformed response 2")]
    )

    mock_api = AsyncMock()
    mock_api.create_feedback = AsyncMock(
        return_value=Feedback(
            id=43, message_id=sample_message.id, profile_id=sample_message.profile_id,
            feedback_type=FeedbackCategory.OTHER, feedback_text="???",
            created_at=datetime.now(timezone.utc),
        )
    )

    with caplog.at_level(logging.WARNING):
        result = await classify_feedback(
            sample_message, "???", claude_client=mock_claude, alerts_api_client=mock_api,
        )

    assert result.feedback_type == FeedbackCategory.OTHER
    assert result.confidence == 0.0
    assert result.classification_failed is True
    assert mock_claude.parse_structured.await_count == 2
    posted = mock_api.create_feedback.await_args.args[0]
    assert posted.feedback_type == FeedbackCategory.OTHER
    assert any(record.levelno == logging.ERROR for record in caplog.records)
