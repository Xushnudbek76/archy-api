import argparse
import json
import sys
from datetime import UTC, datetime
from getpass import getpass
from uuid import UUID

from dotenv import dotenv_values
from sqlalchemy import delete, select

from app.components.accounts.models import AccountSession, User
from app.components.accounts.schemas import EmailRequest
from app.components.accounts.service import invalidate_reset_links
from app.components.courses.models import Course
from app.components.courses.schemas import CourseInput
from app.database.session import create_engine_for, session_factory
from app.libs.config import load_settings
from app.libs.security import hash_password, validate_password


def prompt_password(email):
    password = getpass("Password: ")
    if password != getpass("Confirm password: "):
        raise ValueError("Passwords must match")
    validate_password(password, email)
    return password


def parser():
    result = argparse.ArgumentParser(description="Trusted local Archy administration")
    result.add_argument("--env", default=".env")
    commands = result.add_subparsers(dest="command", required=True)
    for name in ["account-show", "account-create", "account-edit"]:
        command = commands.add_parser(name)
        command.add_argument("email")
        if name != "account-show":
            command.add_argument("--display-name")
            for field in ["active", "staff", "superuser"]:
                command.add_argument("--" + field, choices=["true", "false"])
        if name == "account-edit":
            command.add_argument("--new-email")
            command.add_argument("--set-password", action="store_true")
    for name in ["course-show", "course-edit"]:
        command = commands.add_parser(name)
        command.add_argument("id", type=UUID)
        if name == "course-edit":
            command.add_argument("--title")
            command.add_argument("--owner-id", type=UUID)
            command.add_argument("--archived", choices=["true", "false"])
    return result


def administer(session, args):
    if args.command.startswith("account-"):
        email = str(EmailRequest(email=args.email).email)
        user = session.scalars(select(User).where(User.email == email).with_for_update()).first()
        if args.command == "account-create":
            if user:
                raise ValueError("Account already exists")
            user = User(email=email, password=hash_password(prompt_password(email)))
            session.add(user)
        elif user is None:
            raise ValueError("Account not found")
        previous_email = user.email
        if args.command != "account-show":
            if args.display_name is not None:
                if len(args.display_name.strip()) > 100:
                    raise ValueError("Invalid display name")
                user.display_name = args.display_name.strip()
            for flag in ["active", "staff", "superuser"]:
                value = getattr(args, flag)
                if value is not None:
                    setattr(user, "is_" + flag, value == "true")
            if getattr(args, "new_email", None):
                user.email = str(EmailRequest(email=args.new_email).email)
            if getattr(args, "set_password", False):
                user.password = hash_password(prompt_password(user.email))
            user.updated_at = datetime.now(UTC)
            if user.is_active and user.email_confirmed_at is None:
                user.email_confirmed_at = datetime.now(UTC)
            if user.id and (not user.is_active or getattr(args, "set_password", False)):
                session.execute(delete(AccountSession).where(AccountSession.user_id == user.id))
            if user.id and (
                not user.is_active
                or getattr(args, "set_password", False)
                or user.email != previous_email
            ):
                invalidate_reset_links(session, user.id)
            session.commit()
        return {
            "id": str(user.id),
            "email": user.email,
            "displayName": user.display_name,
            "active": user.is_active,
            "staff": user.is_staff,
            "superuser": user.is_superuser,
        }
    course = session.scalars(select(Course).where(Course.id == args.id).with_for_update()).first()
    if course is None:
        raise ValueError("Course not found")
    if args.command == "course-edit":
        if args.title is not None:
            course.title = CourseInput(title=args.title).title
        if args.owner_id is not None:
            if session.get(User, args.owner_id) is None:
                raise ValueError("Owner not found")
            course.owner_id = args.owner_id
        if args.archived is not None:
            course.archived_at = (
                (course.archived_at or datetime.now(UTC)) if args.archived == "true" else None
            )
        course.updated_at = datetime.now(UTC)
        session.commit()
    return {
        "id": str(course.id),
        "ownerId": str(course.owner_id),
        "title": course.title,
        "archivedAt": course.archived_at.isoformat() if course.archived_at else None,
    }


def main():
    args = parser().parse_args()
    engine = None
    try:
        settings = load_settings(dotenv_values(args.env))
        engine = create_engine_for(settings)
        with session_factory(engine)() as session:
            print(json.dumps(administer(session, args)))
    except Exception:
        print("Administration failed; check inputs and local configuration.", file=sys.stderr)
        return 1
    finally:
        if engine:
            engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
