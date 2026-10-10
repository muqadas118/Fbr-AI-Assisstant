"""Tests for the canonical language module (``app.language``).

Covers detection (Urdu script / Roman Urdu / English), tag normalization,
the reply-language precedence policy, output directives, and localized
constant text.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest

from app.language import (
    LANG_EN,
    LANG_ROMAN_UR,
    LANG_UR,
    LANGUAGES,
    detect_language,
    is_rtl,
    localize,
    normalize_language,
    output_directive,
    resolve_language,
)

ALL_KINDS = (
    "no_evidence",
    "ambiguous_section",
    "unverified",
    "llm_unavailable",
    "placeholder",
)


# ------------------------------------------------------------------
# detect_language
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "اس سیکشن کا مطلب کیا ہے",
        "سیکشن 177 کیا ہے",
        "ٹیکس کی واپسی کب ہوگی",
    ],
)
def test_detect_urdu_script(text):
    assert detect_language(text) == LANG_UR


@pytest.mark.parametrize(
    "text",
    [
        "mujhe salary tax kitna dena hai",
        "income tax return kab file karna hai",
        "mujhe kitna tax dena hai",
        "kaise ye kaam karna hai",
    ],
)
def test_detect_roman_urdu(text):
    assert detect_language(text) == LANG_ROMAN_UR


@pytest.mark.parametrize(
    "text",
    [
        "what is the income tax rate for salaried individuals",
        "important document record",
        "what is the rate",
        "the income tax return filing deadline",
    ],
)
def test_detect_plain_english_not_flagged(text):
    assert detect_language(text) == LANG_EN


@pytest.mark.parametrize("text", ["", None, "hello", "salam", "thanks"])
def test_detect_empty_or_greeting_is_english(text):
    assert detect_language(text) == LANG_EN


def test_detect_returns_canonical_values():
    for text in ("hello", "mujhe kitna tax dena hai", "اس سیکشن کا مطلب کیا ہے"):
        assert detect_language(text) in LANGUAGES


# ------------------------------------------------------------------
# normalize_language
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("tag", "expected"),
    [
        ("roman_urdu", LANG_ROMAN_UR),
        ("roman-ur", LANG_ROMAN_UR),
        ("roman_ur", LANG_ROMAN_UR),
        ("urdu", LANG_UR),
        ("ur", LANG_UR),
        ("english", LANG_EN),
        ("en", LANG_EN),
        ("EN", LANG_EN),
        (None, LANG_EN),
        ("", LANG_EN),
        ("unknown", LANG_EN),
        ("auto", LANG_EN),
        ("klingon", LANG_EN),
    ],
)
def test_normalize_language(tag, expected):
    assert normalize_language(tag) == expected


# ------------------------------------------------------------------
# resolve_language precedence
# ------------------------------------------------------------------


def test_resolve_explicit_preferred_wins():
    assert (
        resolve_language(
            "mujhe salary tax kitna dena hai",
            profile_language=LANG_ROMAN_UR,
            preferred=LANG_EN,
        )
        == LANG_EN
    )


def test_resolve_ignores_auto_and_none_preferred():
    assert (
        resolve_language(
            "mujhe salary tax kitna dena hai",
            profile_language=LANG_EN,
            preferred="auto",
        )
        == LANG_ROMAN_UR
    )
    assert (
        resolve_language(
            "mujhe salary tax kitna dena hai",
            profile_language=LANG_EN,
            preferred=None,
        )
        == LANG_ROMAN_UR
    )


def test_resolve_current_roman_query_beats_english_profile():
    assert (
        resolve_language("mujhe salary tax kitna dena hai", profile_language=LANG_EN)
        == LANG_ROMAN_UR
    )


def test_resolve_current_urdu_query_beats_english_profile():
    assert (
        resolve_language("اس سیکشن کا مطلب کیا ہے", profile_language=LANG_EN)
        == LANG_UR
    )


def test_resolve_english_query_keeps_english():
    assert (
        resolve_language(
            "what is the income tax rate for salaried individuals",
            profile_language=LANG_ROMAN_UR,
        )
        == LANG_EN
    )


def test_resolve_empty_query_falls_back_to_profile():
    assert resolve_language("", profile_language=LANG_ROMAN_UR) == LANG_ROMAN_UR


def test_resolve_empty_query_no_profile_defaults_english():
    assert resolve_language("", profile_language=None) == LANG_EN


def test_resolve_latin_greeting_is_english_signal():
    # >= 2 latin letters counts as an English signal (contract rule).
    assert resolve_language("hello", profile_language=LANG_UR) == LANG_EN


def test_resolve_non_latin_short_falls_back_to_profile():
    # No latin letters -> not an English signal -> profile wins.
    assert resolve_language("!!", profile_language=LANG_UR) == LANG_UR


def test_resolve_never_raises_on_odd_input():
    assert resolve_language(None) == LANG_EN  # type: ignore[arg-type]
    assert resolve_language("x", profile_language="garbage") == LANG_EN


# ------------------------------------------------------------------
# is_rtl
# ------------------------------------------------------------------


def test_is_rtl():
    assert is_rtl(LANG_UR) is True
    assert is_rtl("urdu") is True
    assert is_rtl(LANG_EN) is False
    assert is_rtl(LANG_ROMAN_UR) is False
    assert is_rtl("unknown") is False


# ------------------------------------------------------------------
# output_directive
# ------------------------------------------------------------------


@pytest.mark.parametrize(
    ("lang", "script_marker"),
    [
        (LANG_EN, "English"),
        (LANG_ROMAN_UR, "Roman Urdu"),
        (LANG_UR, "Urdu script"),
    ],
)
def test_output_directive_has_script_and_figure_rule(lang, script_marker):
    directive = output_directive(lang)
    assert script_marker in directive
    assert "retrieved evidence" in directive
    assert "never translate" in directive


def test_output_directive_unknown_lang_defaults_english():
    assert output_directive("klingon") == output_directive(LANG_EN)


# ------------------------------------------------------------------
# localize
# ------------------------------------------------------------------


@pytest.mark.parametrize("kind", ALL_KINDS)
def test_localize_non_empty_and_languages_differ(kind):
    values = {lang: localize(kind, lang) for lang in LANGUAGES}
    for value in values.values():
        assert isinstance(value, str) and value.strip()
    assert len(set(values.values())) == 3


def test_localize_unknown_lang_defaults_english():
    assert localize("placeholder", "klingon") == localize("placeholder", LANG_EN)


def test_localize_unknown_kind_raises_keyerror():
    with pytest.raises(KeyError):
        localize("not_a_kind", LANG_EN)
