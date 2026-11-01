from uuid import UUID

from sqlalchemy import func, select

from app.components.academics.service import lock_owner
from app.components.accounts.models import User, now
from app.components.preferences.models import NoteFormat, Profile
from app.libs.errors import ApiError

FORMATS = [
    {
        "id": "outline",
        "name": "Clear outline",
        "instructions": "",
        "description": "Key concepts, examples, and questions for review.",
    },
    {
        "id": "cornell",
        "name": "Cornell notes",
        "instructions": (
            "Use short questions as retrieval cues, pair them with explanatory notes, "
            "and end with a concise recap. Keep the required JSON schema unchanged."
        ),
        "description": "Study cues alongside clear explanations and a short recap.",
    },
    {
        "id": "review",
        "name": "Exam review",
        "instructions": (
            "Prioritize retrieval practice: emphasize key concepts, likely points of confusion, "
            "and questions for self-testing. Keep the required JSON schema unchanged "
            "and use only supplied material."
        ),
        "description": "Focus on the ideas you need to recall and explain.",
    },
]


def format_for(session, owner_id, key):
    preset = next((item for item in FORMATS if item["id"] == key), None)
    if preset:
        return {**preset, "custom": False}
    try:
        identifier = UUID(key)
    except (ValueError, TypeError):
        raise ApiError(404) from None
    item = session.scalar(
        select(NoteFormat).where(NoteFormat.id == identifier, NoteFormat.owner_id == owner_id)
    )
    if item is None:
        raise ApiError(404)
    return {
        "id": str(item.id),
        "name": item.name,
        "instructions": item.instructions,
        "description": "Your custom note structure.",
        "custom": True,
    }


def read_profile(session, owner_id):
    user = session.get(User, owner_id)
    profile = session.get(Profile, owner_id)
    return {
        "displayName": user.display_name,
        "email": user.email,
        "university": profile.university if profile else "",
        "department": profile.department if profile else "",
        "uiLanguage": profile.ui_language if profile else "en",
        "summaryLanguage": profile.summary_language if profile else "auto",
        "noteFormat": profile.note_format if profile else "outline",
    }


def update_profile(session, owner_id, data):
    lock_owner(session, owner_id)
    if "noteFormat" in data.model_fields_set:
        format_for(session, owner_id, data.noteFormat)
    profile = session.get(Profile, owner_id)
    if profile is None:
        profile = Profile(owner_id=owner_id)
        session.add(profile)
    if "displayName" in data.model_fields_set:
        user = session.get(User, owner_id)
        user.display_name = data.displayName
        user.updated_at = now()
    for field, attribute in [
        ("university", "university"),
        ("department", "department"),
        ("uiLanguage", "ui_language"),
        ("summaryLanguage", "summary_language"),
        ("noteFormat", "note_format"),
    ]:
        if field in data.model_fields_set:
            setattr(profile, attribute, getattr(data, field))
    profile.updated_at = now()
    session.commit()
    return read_profile(session, owner_id)


def list_formats(session, owner_id):
    custom = session.scalars(
        select(NoteFormat).where(NoteFormat.owner_id == owner_id).order_by(NoteFormat.created_at)
    ).all()
    return {
        "items": [{**item, "custom": False} for item in FORMATS]
        + [
            {
                "id": str(item.id),
                "name": item.name,
                "instructions": item.instructions,
                "description": "Your custom note structure.",
                "custom": True,
            }
            for item in custom
        ]
    }


def create_format(session, owner_id, data):
    lock_owner(session, owner_id)
    if (
        session.scalar(
            select(func.count()).select_from(NoteFormat).where(NoteFormat.owner_id == owner_id)
        )
        >= 10
    ):
        raise ApiError(400, "format_limit", "You can save up to 10 custom note formats.")
    item = NoteFormat(owner_id=owner_id, name=data.name, instructions=data.instructions)
    session.add(item)
    session.commit()
    return format_for(session, owner_id, str(item.id))


def update_format(session, owner_id, key, data):
    lock_owner(session, owner_id)
    format_for(session, owner_id, str(key))
    item = session.get(NoteFormat, key)
    item.name, item.instructions = data.name, data.instructions
    session.commit()
    return format_for(session, owner_id, str(item.id))


def archive_format(session, owner_id, key):
    lock_owner(session, owner_id)
    format_for(session, owner_id, str(key))
    profile = session.get(Profile, owner_id)
    if profile and profile.note_format == str(key):
        profile.note_format = "outline"
    session.delete(session.get(NoteFormat, key))
    session.commit()
    return {"removed": True}


def processing_preferences(session, owner_id):
    profile = read_profile(session, owner_id)
    style = format_for(session, owner_id, profile["noteFormat"])
    return {
        "summary_language": None
        if profile["summaryLanguage"] == "auto"
        else profile["summaryLanguage"],
        "note_instructions": style["instructions"],
    }
