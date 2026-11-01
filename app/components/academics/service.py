from datetime import UTC, datetime

from sqlalchemy import func, select, update

from app.components.academics.models import AcademicSelection, AcademicTerm, Timetable
from app.components.accounts.models import User
from app.libs.errors import ApiError


def serialize_term(term):
    return {
        "id": term.id,
        "name": term.name,
        "archivedAt": term.archived_at,
        "createdAt": term.created_at,
    }


def serialize_timetable(table):
    return {
        "id": table.id,
        "termId": table.term_id,
        "name": table.name,
        "isPrimary": table.is_primary,
        "createdAt": table.created_at,
    }


def lock_owner(session, owner_id):
    active = session.scalar(
        select(User.id).where(User.id == owner_id, User.is_active.is_(True)).with_for_update()
    )
    if active is None:
        raise ApiError(403)


def term_for(session, owner_id, key, *, writable=False):
    term = session.scalar(
        select(AcademicTerm).where(AcademicTerm.id == key, AcademicTerm.owner_id == owner_id)
    )
    if term is None:
        raise ApiError(404)
    if writable and term.archived_at is not None:
        raise ApiError(409, "term_archived", "This semester is archived and read-only.")
    return term


def timetable_for(session, owner_id, key, *, writable=False):
    table = session.scalar(
        select(Timetable).where(Timetable.id == key, Timetable.owner_id == owner_id)
    )
    if table is None:
        raise ApiError(404)
    term_for(session, owner_id, table.term_id, writable=writable)
    return table


def overview(session, owner_id):
    terms = session.scalars(
        select(AcademicTerm)
        .where(AcademicTerm.owner_id == owner_id)
        .order_by(AcademicTerm.created_at.desc(), AcademicTerm.id)
    ).all()
    tables = session.scalars(
        select(Timetable)
        .where(Timetable.owner_id == owner_id)
        .order_by(Timetable.created_at, Timetable.id)
    ).all()
    active_terms = {term.id for term in terms if term.archived_at is None}
    active_tables = {table.id for table in tables if table.term_id in active_terms}
    selection = session.get(AcademicSelection, owner_id)
    selected = (
        selection.timetable_id if selection and selection.timetable_id in active_tables else None
    )
    if selected is None:
        for term in terms:
            if term.id not in active_terms:
                continue
            selected = next(
                (table.id for table in tables if table.term_id == term.id and table.is_primary),
                None,
            )
            if selected:
                break
    return {
        "terms": [serialize_term(term) for term in terms],
        "timetables": [serialize_timetable(table) for table in tables],
        "selectedTimetableId": selected,
    }


def check_count(session, model, owner_id):
    if (
        session.scalar(select(func.count()).select_from(model).where(model.owner_id == owner_id))
        >= 100
    ):
        raise ApiError(400, "academic_limit", "The workspace limit of 100 items has been reached.")


def create_term(session, owner_id, data):
    lock_owner(session, owner_id)
    check_count(session, AcademicTerm, owner_id)
    term = AcademicTerm(owner_id=owner_id, name=data.name)
    session.add(term)
    session.commit()
    return serialize_term(term)


def rename_term(session, owner_id, key, data):
    lock_owner(session, owner_id)
    term = term_for(session, owner_id, key, writable=True)
    term.name = data.name
    session.commit()
    return serialize_term(term)


def archive_term(session, owner_id, key):
    lock_owner(session, owner_id)
    term = term_for(session, owner_id, key)
    term.archived_at = term.archived_at or datetime.now(UTC)
    session.commit()
    return serialize_term(term)


def create_timetable(session, owner_id, data):
    lock_owner(session, owner_id)
    term_for(session, owner_id, data.termId, writable=True)
    check_count(session, Timetable, owner_id)
    first = session.scalar(select(Timetable.id).where(Timetable.term_id == data.termId)) is None
    table = Timetable(owner_id=owner_id, term_id=data.termId, name=data.name, is_primary=first)
    session.add(table)
    session.commit()
    return serialize_timetable(table)


def rename_timetable(session, owner_id, key, data):
    lock_owner(session, owner_id)
    table = timetable_for(session, owner_id, key, writable=True)
    table.name = data.name
    session.commit()
    return serialize_timetable(table)


def select_timetable(session, owner_id, key):
    lock_owner(session, owner_id)
    timetable_for(session, owner_id, key, writable=True)
    selection = session.get(AcademicSelection, owner_id)
    if selection is None:
        session.add(AcademicSelection(owner_id=owner_id, timetable_id=key))
    else:
        selection.timetable_id = key
    session.commit()
    return overview(session, owner_id)


def make_primary(session, owner_id, key):
    lock_owner(session, owner_id)
    table = timetable_for(session, owner_id, key, writable=True)
    session.execute(
        update(Timetable).where(Timetable.term_id == table.term_id).values(is_primary=False)
    )
    session.flush()
    table.is_primary = True
    session.commit()
    return serialize_timetable(table)
