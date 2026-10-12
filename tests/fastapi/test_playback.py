import pytest

from app.components.recordings.playback import byte_range


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        (None, None),
        ("bytes=9-2", None),
        ("bytes=bad", None),
        ("items=0-1", None),
        ("bytes=0-1,8-9", None),
        ("bytes=20-30,0-1", None),
        ("bytes=" + "1" * 101 + "-", None),
        ("bytes=-2", (8, 9)),
        ("bytes=2-", (2, 9)),
        ("bytes=2-100", (2, 9)),
    ],
)
def test_ranges_use_partial_or_full_response(header, expected):
    assert byte_range(header, 10) == expected


@pytest.mark.parametrize("header", ["bytes=20-30", "bytes=20-30,40-50", "bytes=-0"])
def test_valid_ranges_without_overlap_raise(header):
    with pytest.raises(ValueError):
        byte_range(header, 10)
