import re
import time
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit

import httpx
from pydantic import ValidationError

from app.components.courses.schemas import CourseCreate
from app.libs.errors import ApiError

MAX_BYTES = 2 * 1024 * 1024
COLORS = ["#396c50", "#596e9d", "#986b45", "#77629b", "#4b7d85", "#a15f6e"]


def invalid():
    return ApiError(
        400, "invalid_timetable", "Use a public Everytime share link, or add your courses manually."
    )


def share_identifier(value):
    try:
        url = urlsplit(value.strip())
        match = re.fullmatch(r"/(?:app/)?@([A-Za-z0-9_-]{1,100})/?", url.path)
        if (
            url.scheme != "https"
            or url.hostname not in {"everytime.kr", "www.everytime.kr"}
            or url.username
            or url.password
            or url.port not in {None, 443}
            or url.query
            or url.fragment
            or not match
        ):
            raise invalid()
        return match[1]
    except (ValueError, AttributeError):
        raise invalid() from None


def fetch_public(identifier):
    started = time.monotonic()
    try:
        with httpx.Client(timeout=12, follow_redirects=False) as client:
            with client.stream(
                "POST",
                "https://api.everytime.kr/find/timetable/table/friend",
                data={"identifier": identifier, "friendInfo": "true"},
                headers={
                    "Accept": "application/xml,text/xml",
                    "User-Agent": "ArchyTimetableImport/1.0",
                    "Referer": f"https://everytime.kr/@{identifier}",
                },
            ) as response:
                if response.status_code != 200:
                    raise ApiError(
                        502,
                        "import_unavailable",
                        "Everytime could not provide this public timetable. "
                        "Try again later or add courses manually.",
                    )
                data = bytearray()
                for chunk in response.iter_bytes(64 * 1024):
                    data.extend(chunk)
                    if len(data) > MAX_BYTES or time.monotonic() - started > 18:
                        raise invalid()
                return bytes(data)
    except httpx.HTTPError:
        raise ApiError(
            502, "import_unavailable", "Everytime is temporarily unavailable. Please try again."
        ) from None


def parse_timetable(data):
    try:
        text = data.decode("utf-8-sig")
        if (
            len(data) > MAX_BYTES
            or "<!DOCTYPE" in text.upper()
            or "<!ENTITY" in text.upper()
            or "\x00" in text
        ):
            raise invalid()
        root = ET.fromstring(text)
        if sum(1 for _ in root.iter()) > 5000:
            raise invalid()
        result = []
        for index, subject in enumerate(root.iter("subject")):
            if index >= 50:
                raise invalid()
            name, professor = subject.find("name"), subject.find("professor")
            title = name.get("value", "") if name is not None else ""
            slots = []
            for slot in subject.iter("data"):
                start, end = int(slot.attrib["starttime"]) * 5, int(slot.attrib["endtime"]) * 5
                slots.append(
                    {
                        "days": [int(slot.attrib["day"])],
                        "startTime": f"{start // 60:02d}:{start % 60:02d}",
                        "endTime": f"{end // 60:02d}:{end % 60:02d}",
                        "room": slot.get("place", ""),
                    }
                )
            if not slots:
                continue
            item = CourseCreate.model_validate(
                {
                    "title": title,
                    "professor": professor.get("value", "") if professor is not None else "",
                    "color": COLORS[index % len(COLORS)],
                    "schedules": slots,
                }
            )
            result.append(item.model_dump(mode="json", exclude={"timetableId"}))
        if not result:
            raise invalid()
        return result
    except (ET.ParseError, KeyError, ValueError, ValidationError, UnicodeError):
        raise invalid() from None
