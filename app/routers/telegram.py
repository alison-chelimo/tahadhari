import logging
import os
import asyncio

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from ..database import commit_or_error, get_db
from ..models import Feedback, Message, Profile, RegistrationRequest, TelegramOnboardingState

router = APIRouter()
logger = logging.getLogger(__name__)

STATE_AWAIT_COUNTY = "await_county"
STATE_AWAIT_TOWN = "await_town"
STATE_AWAIT_OCCUPATION = "await_occupation"
STATE_AWAIT_KEY_ASSET = "await_key_asset"
STATE_AWAIT_OCCUPATION_AMEND = "await_occupation_amend"

COUNTY_TOWNS: dict[str, list[str]] = {
    "Baringo": ["Kabarnet", "Marigat", "Eldama Ravine"],
    "Bomet": ["Bomet", "Sotik", "Longisa"],
    "Bungoma": ["Bungoma", "Webuye", "Kimilili"],
    "Busia": ["Busia", "Malaba", "Nambale"],
    "Elgeyo-Marakwet": ["Iten", "Kapsowar", "Tambach"],
    "Embu": ["Embu", "Runyenjes", "Siakago"],
    "Garissa": ["Garissa", "Dadaab", "Hulugho"],
    "Homa Bay": ["Homa Bay", "Mbita", "Oyugis"],
    "Isiolo": ["Isiolo", "Merti", "Garbatulla"],
    "Kajiado": ["Kajiado", "Ngong", "Kitengela"],
    "Kakamega": ["Kakamega", "Mumias", "Malava"],
    "Kericho": ["Kericho", "Litein", "Londiani"],
    "Kiambu": ["Kiambu", "Thika", "Ruiru"],
    "Kilifi": ["Kilifi", "Malindi", "Mtwapa"],
    "Kirinyaga": ["Kerugoya", "Kagio", "Mwea"],
    "Kisii": ["Kisii", "Ogembo", "Suneka"],
    "Kisumu": ["Kisumu", "Ahero", "Muhoroni"],
    "Kitui": ["Kitui", "Mwingi", "Mutomo"],
    "Kwale": ["Kwale", "Ukunda", "Lungalunga"],
    "Laikipia": ["Nanyuki", "Nyahururu", "Rumuruti"],
    "Lamu": ["Lamu", "Mpeketoni", "Faza"],
    "Machakos": ["Machakos", "Mavoko", "Kangundo"],
    "Makueni": ["Wote", "Emali", "Makindu"],
    "Mandera": ["Mandera", "El Wak", "Rhamu"],
    "Marsabit": ["Marsabit", "Moyale", "Laisamis"],
    "Meru": ["Meru", "Maua", "Nkubu"],
    "Migori": ["Migori", "Rongo", "Awendo"],
    "Mombasa": ["Mombasa", "Kisauni", "Likoni"],
    "Murang'a": ["Murang'a", "Kenol", "Kangema"],
    "Nairobi City": ["Nairobi", "Westlands", "Embakasi"],
    "Nakuru": ["Nakuru", "Naivasha", "Molo"],
    "Nandi": ["Kapsabet", "Nandi Hills", "Mosoriot"],
    "Narok": ["Narok", "Kilgoris", "Suswa"],
    "Nyamira": ["Nyamira", "Keroka", "Nyansiongo"],
    "Nyandarua": ["Ol Kalou", "Njabini", "Engineer"],
    "Nyeri": ["Nyeri", "Karatina", "Othaya"],
    "Samburu": ["Maralal", "Baragoi", "Archers Post"],
    "Siaya": ["Siaya", "Bondo", "Ugunja"],
    "Taita-Taveta": ["Voi", "Taveta", "Wundanyi"],
    "Tana River": ["Hola", "Bura", "Garsen"],
    "Tharaka-Nithi": ["Chuka", "Kathwana", "Marimanti"],
    "Trans Nzoia": ["Kitale", "Kiminini", "Endebess"],
    "Turkana": ["Lodwar", "Kakuma", "Lokichoggio"],
    "Uasin Gishu": ["Eldoret", "Burnt Forest", "Turbo"],
    "Vihiga": ["Mbale", "Luanda", "Chavakali"],
    "Wajir": ["Wajir", "Habaswein", "Griftu"],
    "West Pokot": ["Kapenguria", "Makutano", "Ortum"],
}

WEATHER_AFFECTED_OCCUPATIONS = [
    "Farmer",
    "Fisher",
    "Pastoralist",
    "Boda boda rider",
    "Driver",
    "Market trader",
    "Construction worker",
    "Small business owner",
    "Teacher",
    "Healthcare worker",
]

REMOVE_KEYBOARD = {"remove_keyboard": True}


def _send_telegram_text(chat_id: str, text: str, reply_markup: dict | None = None) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        logger.warning("TELEGRAM_BOT_TOKEN is not set; skipping outbound bot reply")
        return

    endpoint = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": text}
    if reply_markup is not None:
        payload["reply_markup"] = reply_markup

    response = httpx.post(endpoint, json=payload, timeout=15.0)
    if response.status_code >= 400:
        logger.warning("Failed to send Telegram bot reply: %s %s", response.status_code, response.text)
        return

    try:
        body = response.json()
    except ValueError:
        return

    if body.get("ok") is False:
        logger.warning("Telegram sendMessage returned ok=false: %s", body)


def _build_inline_keyboard(options: list[str], prefix: str, columns: int = 2, include_cancel: bool = True) -> dict:
    keyboard: list[list[dict[str, str]]] = []
    for idx in range(0, len(options), columns):
        row = [
            {"text": option, "callback_data": f"{prefix}:{option}"}
            for option in options[idx : idx + columns]
        ]
        keyboard.append(row)
    if include_cancel:
        keyboard.append([{"text": "Cancel", "callback_data": "action:cancel"}])
    return {"inline_keyboard": keyboard}


def _answer_telegram_callback(callback_query_id: str) -> None:
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not bot_token:
        return
    endpoint = f"https://api.telegram.org/bot{bot_token}/answerCallbackQuery"
    try:
        httpx.post(endpoint, json={"callback_query_id": callback_query_id}, timeout=10.0)
    except Exception:
        logger.exception("Failed to answer Telegram callback query")


def _match_option(input_text: str, options: list[str]) -> str | None:
    normalized = input_text.strip().casefold()
    for option in options:
        if normalized == option.casefold():
            return option
    return None


async def _generate_ai_reply(profile: Profile, user_text: str) -> str:
    try:
        from ai_layer.clients.openai_client import OpenAIClient, OpenAIClientError
    except Exception:
        logger.exception("OpenAI client unavailable; using fallback text")
        return (
            "I can help with safety guidance and preparedness tips. "
            "If you need to update your occupation, use /occupation."
        )

    openai_client = OpenAIClient()
    system = (
        "You are Tahadhari Assistant for climate and flood risk guidance in Tanzania. "
        "Give concise, practical, safety-first advice. "
        "Do not claim to have real-time data unless provided in context."
    )
    user_content = (
        f"User profile: user_type={profile.user_type}, occupation={profile.occupation}, "
        f"ward={profile.ward}, route_id={profile.route_id}, key_asset={profile.key_asset}.\n"
        f"User message: {user_text}"
    )
    fallback = (
        "I can help with safety guidance and preparedness tips. "
        "If you need to update your occupation, use /occupation."
    )

    try:
        reply = (await openai_client.create_text(system=system, user_content=user_content, max_tokens=220)).strip()
        if not reply:
            return fallback
        return reply
    except OpenAIClientError:
        logger.exception("AI reply generation failed; using fallback text")
        return fallback
    finally:
        await openai_client.aclose()


def _generate_ai_reply_sync(profile: Profile, user_text: str) -> str:
    return asyncio.run(_generate_ai_reply(profile, user_text))


def _get_or_create_state(db: Session, chat_id: str) -> TelegramOnboardingState:
    state = db.query(TelegramOnboardingState).filter(TelegramOnboardingState.chat_id == chat_id).first()
    if state:
        return state

    state = TelegramOnboardingState(chat_id=chat_id, state=STATE_AWAIT_COUNTY, draft_json={})
    commit_or_error(db, state, resource_name="telegram onboarding state")
    return state


def _reset_state(db: Session, chat_id: str) -> TelegramOnboardingState:
    state = db.query(TelegramOnboardingState).filter(TelegramOnboardingState.chat_id == chat_id).first()
    if state:
        state.state = STATE_AWAIT_COUNTY
        state.draft_json = {}
        commit_or_error(db, state, resource_name="telegram onboarding state")
        return state
    return _get_or_create_state(db, chat_id)


def _clear_state(db: Session, state: TelegramOnboardingState) -> None:
    db.delete(state)
    db.commit()


def _get_profile_by_chat_id(db: Session, chat_id: str) -> Profile | None:
    return db.query(Profile).filter(Profile.phone_number == chat_id).first()


def _set_occupation_amend_state(db: Session, chat_id: str) -> TelegramOnboardingState:
    state = db.query(TelegramOnboardingState).filter(TelegramOnboardingState.chat_id == chat_id).first()
    if state is None:
        state = TelegramOnboardingState(chat_id=chat_id, state=STATE_AWAIT_OCCUPATION_AMEND, draft_json={})
        commit_or_error(db, state, resource_name="telegram onboarding state")
        return state

    state.state = STATE_AWAIT_OCCUPATION_AMEND
    state.draft_json = {}
    commit_or_error(db, state, resource_name="telegram onboarding state")
    return state


def _is_dev_reset_enabled() -> bool:
    value = os.getenv("TELEGRAM_ENABLE_DEV_RESET", "").strip().casefold()
    return value in {"1", "true", "yes", "on"}


def _reset_test_user_data(db: Session, chat_id: str) -> bool:
    state = db.query(TelegramOnboardingState).filter(TelegramOnboardingState.chat_id == chat_id).first()
    profile = db.query(Profile).filter(Profile.phone_number == chat_id).first()

    if state is None and profile is None:
        return False

    if state is not None:
        db.delete(state)

    if profile is not None:
        db.query(Feedback).filter(Feedback.profile_id == profile.id).delete(synchronize_session=False)
        db.query(Message).filter(Message.profile_id == profile.id).delete(synchronize_session=False)
        db.query(RegistrationRequest).filter(
            (RegistrationRequest.profile_id == profile.id) | (RegistrationRequest.phone_number == chat_id)
        ).delete(synchronize_session=False)
        db.delete(profile)
    else:
        db.query(RegistrationRequest).filter(RegistrationRequest.phone_number == chat_id).delete(synchronize_session=False)

    db.commit()
    return True


def _save_profile_from_draft(db: Session, chat_id: str, draft: dict) -> Profile:
    profile = db.query(Profile).filter(Profile.phone_number == chat_id).first()

    user_type = "rural"
    county = (draft.get("county") or "").strip()
    town = (draft.get("town") or "").strip()
    occupation = (draft.get("occupation") or "").strip()
    key_asset = (draft.get("key_asset") or "").strip()
    if not county or not town or not occupation or not key_asset:
        raise ValueError("county, town, occupation, and key_asset are required")

    ward = f"{town}, {county}"
    route_id = None

    if profile is None:
        profile = Profile(
            phone_number=chat_id,
            channel="telegram",
            language="en",
            user_type=user_type,
            occupation=occupation,
            ward=ward,
            route_id=route_id,
            key_asset=key_asset,
            registration_source="partner_assisted",
            registered_by="telegram_bot",
        )
        commit_or_error(db, profile, resource_name="profile")
        return profile

    profile.channel = "telegram"
    profile.language = profile.language or "en"
    profile.user_type = user_type
    profile.occupation = occupation
    profile.ward = ward
    profile.route_id = route_id
    profile.key_asset = key_asset
    profile.registration_source = "partner_assisted"
    profile.registered_by = "telegram_bot"
    commit_or_error(db, profile, resource_name="profile")
    return profile


def _prompt_for_current_state(chat_id: str, state_value: str, draft: dict | None = None) -> None:
    if state_value == STATE_AWAIT_COUNTY:
        counties = list(COUNTY_TOWNS.keys())
        counties_text = "\n".join(f"- {county}" for county in counties)
        _send_telegram_text(
            chat_id,
            f"Welcome to Tahadhari. Select your county from the buttons below.\n\nAvailable counties:\n{counties_text}",
            reply_markup=_build_inline_keyboard(counties, prefix="county", columns=2),
        )
    elif state_value == STATE_AWAIT_TOWN:
        selected_county = (draft or {}).get("county")
        towns = COUNTY_TOWNS.get(selected_county, [])
        if towns:
            towns_text = "\n".join(f"- {town}" for town in towns)
            _send_telegram_text(
                chat_id,
                (
                    f"Select your town in {selected_county} from the buttons below.\n\n"
                    f"Major towns:\n{towns_text}"
                ),
                reply_markup=_build_inline_keyboard(towns, prefix="town", columns=2),
            )
        else:
            _send_telegram_text(chat_id, "Please select your town.")
    elif state_value == STATE_AWAIT_OCCUPATION:
        occupations_text = "\n".join(f"- {occupation}" for occupation in WEATHER_AFFECTED_OCCUPATIONS)
        _send_telegram_text(
            chat_id,
            (
                "Select your occupation from the buttons below.\n\n"
                "Weather-sensitive occupations:\n"
                f"{occupations_text}"
            ),
            reply_markup=_build_inline_keyboard(WEATHER_AFFECTED_OCCUPATIONS, prefix="occupation", columns=2),
        )
    elif state_value == STATE_AWAIT_KEY_ASSET:
        _send_telegram_text(chat_id, "Please enter your key asset (e.g., maize farm, fishing boat).")
    elif state_value == STATE_AWAIT_OCCUPATION_AMEND:
        occupations_text = "\n".join(f"- {occupation}" for occupation in WEATHER_AFFECTED_OCCUPATIONS)
        _send_telegram_text(
            chat_id,
            (
                "Select your new occupation from the buttons below.\n\n"
                "Weather-sensitive occupations:\n"
                f"{occupations_text}"
            ),
            reply_markup=_build_inline_keyboard(WEATHER_AFFECTED_OCCUPATIONS, prefix="occupation", columns=2),
        )


@router.post("/webhook")
def telegram_webhook(
    payload: dict,
    db: Session = Depends(get_db),
    telegram_secret: str | None = Header(default=None, alias="X-Telegram-Bot-Api-Secret-Token"),
):
    expected_secret = os.getenv("TELEGRAM_WEBHOOK_SECRET", "").strip()
    if expected_secret and telegram_secret != expected_secret:
        raise HTTPException(status_code=401, detail="Invalid Telegram webhook secret")

    callback_query = payload.get("callback_query") or {}
    callback_data = (callback_query.get("data") or "").strip()
    callback_id = callback_query.get("id")
    callback_message = callback_query.get("message") or {}

    message = payload.get("message") or {}
    text = (message.get("text") or "").strip()
    chat = message.get("chat") or {}
    chat_id_raw = chat.get("id")

    if callback_data and (not text):
        chat = callback_message.get("chat") or {}
        chat_id_raw = chat.get("id")
        if callback_data.startswith("county:"):
            text = callback_data.split(":", 1)[1].strip()
        elif callback_data.startswith("town:"):
            text = callback_data.split(":", 1)[1].strip()
        elif callback_data.startswith("occupation:"):
            text = callback_data.split(":", 1)[1].strip()
        elif callback_data == "action:cancel":
            text = "/cancel"
        if callback_id:
            _answer_telegram_callback(callback_id)

    if chat_id_raw is None or not text:
        return {"ok": True, "detail": "ignored"}

    chat_id = str(chat_id_raw)
    lowered = text.casefold()
    profile = _get_profile_by_chat_id(db, chat_id)

    if lowered == "/start":
        if profile is not None:
            _send_telegram_text(
                chat_id,
                "You are already registered. Use /occupation to update your occupation.",
            )
            return {"ok": True, "detail": "already_registered", "profile_id": profile.id}
        _reset_state(db, chat_id)
        _prompt_for_current_state(chat_id, STATE_AWAIT_COUNTY)
        return {"ok": True, "detail": "started"}

    if lowered == "/occupation":
        if profile is None:
            _send_telegram_text(chat_id, "You are not registered yet. Send /start to begin registration.")
            return {"ok": True, "detail": "not_registered"}
        _set_occupation_amend_state(db, chat_id)
        _prompt_for_current_state(chat_id, STATE_AWAIT_OCCUPATION_AMEND)
        return {"ok": True, "detail": "await_occupation_amend", "profile_id": profile.id}

    if lowered == "/cancel":
        state = db.query(TelegramOnboardingState).filter(TelegramOnboardingState.chat_id == chat_id).first()
        if state:
            _clear_state(db, state)
        _send_telegram_text(chat_id, "Registration canceled. Send /start to begin again.")
        return {"ok": True, "detail": "canceled"}

    if lowered == "/resetme":
        if not _is_dev_reset_enabled():
            _send_telegram_text(chat_id, "This command is disabled.")
            return {"ok": True, "detail": "reset_disabled"}

        reset_performed = _reset_test_user_data(db, chat_id)
        _send_telegram_text(
            chat_id,
            "Test account reset complete. Send /start to register again."
            if reset_performed
            else "No registration data found for this chat. Send /start to begin.",
        )
        return {"ok": True, "detail": "reset_done" if reset_performed else "reset_noop"}

    state = db.query(TelegramOnboardingState).filter(TelegramOnboardingState.chat_id == chat_id).first()
    if state is None:
        if profile is not None:
            if lowered.startswith("/"):
                _send_telegram_text(
                    chat_id,
                    "Unknown command. Use /occupation to update your occupation.",
                )
                return {"ok": True, "detail": "unknown_command", "profile_id": profile.id}

            ai_reply = _generate_ai_reply_sync(profile, text)
            _send_telegram_text(chat_id, ai_reply)
            return {"ok": True, "detail": "ai_reply_sent", "profile_id": profile.id}
        _send_telegram_text(chat_id, "Send /start to begin registration.")
        return {"ok": True, "detail": "no_state"}

    draft = dict(state.draft_json or {})

    if state.state == STATE_AWAIT_COUNTY:
        selected_county = _match_option(text, list(COUNTY_TOWNS.keys()))
        if selected_county is None:
            _send_telegram_text(
                chat_id,
                "Invalid county. Please select a county from the buttons.",
                reply_markup=_build_inline_keyboard(list(COUNTY_TOWNS.keys()), prefix="county", columns=2),
            )
            return {"ok": True, "detail": "invalid_county"}

        draft["county"] = selected_county
        state.state = STATE_AWAIT_TOWN
        state.draft_json = draft
        commit_or_error(db, state, resource_name="telegram onboarding state")
        _prompt_for_current_state(chat_id, state.state, draft)
        return {"ok": True, "detail": "advanced"}

    if state.state == STATE_AWAIT_TOWN:
        selected_county = draft.get("county")
        town_options = COUNTY_TOWNS.get(selected_county, [])
        selected_town = _match_option(text, town_options)
        if selected_town is None:
            if town_options:
                _send_telegram_text(
                    chat_id,
                    "Invalid town. Please select a town from the buttons.",
                    reply_markup=_build_inline_keyboard(town_options, prefix="town", columns=2),
                )
            else:
                _send_telegram_text(chat_id, "Invalid town. Please select your town from the list.")
            return {"ok": True, "detail": "invalid_town"}

        draft["town"] = selected_town
        state.state = STATE_AWAIT_OCCUPATION
        state.draft_json = draft
        commit_or_error(db, state, resource_name="telegram onboarding state")
        _prompt_for_current_state(chat_id, state.state, draft)
        return {"ok": True, "detail": "advanced"}

    if state.state == STATE_AWAIT_OCCUPATION:
        selected_occupation = _match_option(text, WEATHER_AFFECTED_OCCUPATIONS)
        if selected_occupation is None:
            _send_telegram_text(
                chat_id,
                "Invalid occupation. Please select an occupation from the buttons.",
                reply_markup=_build_inline_keyboard(
                    WEATHER_AFFECTED_OCCUPATIONS,
                    prefix="occupation",
                    columns=2,
                ),
            )
            return {"ok": True, "detail": "invalid_occupation"}

        draft["occupation"] = selected_occupation
        state.state = STATE_AWAIT_KEY_ASSET
        state.draft_json = draft
        commit_or_error(db, state, resource_name="telegram onboarding state")
        _prompt_for_current_state(chat_id, state.state, draft)
        return {"ok": True, "detail": "advanced"}

    if state.state == STATE_AWAIT_KEY_ASSET:
        draft["key_asset"] = text
        state.draft_json = draft
        profile = _save_profile_from_draft(db, chat_id, draft)
        _clear_state(db, state)
        _send_telegram_text(
            chat_id,
            f"Registration complete. Your profile ID is {profile.id}. You will now receive Tahadhari alerts here.",
        )
        return {"ok": True, "detail": "registered", "profile_id": profile.id}

    if state.state == STATE_AWAIT_OCCUPATION_AMEND:
        new_occupation = _match_option(text, WEATHER_AFFECTED_OCCUPATIONS)
        if new_occupation is None:
            _send_telegram_text(
                chat_id,
                "Invalid occupation. Please select your new occupation from the buttons.",
                reply_markup=_build_inline_keyboard(
                    WEATHER_AFFECTED_OCCUPATIONS,
                    prefix="occupation",
                    columns=2,
                ),
            )
            return {"ok": True, "detail": "invalid_occupation"}

        if profile is None:
            _clear_state(db, state)
            _send_telegram_text(chat_id, "You are not registered yet. Send /start to begin registration.")
            return {"ok": True, "detail": "not_registered"}

        profile.occupation = new_occupation
        commit_or_error(db, profile, resource_name="profile")
        _clear_state(db, state)
        _send_telegram_text(chat_id, f"Occupation updated to: {new_occupation}")
        return {"ok": True, "detail": "occupation_updated", "profile_id": profile.id}

    _prompt_for_current_state(chat_id, state.state)
    return {"ok": True, "detail": "prompted"}
