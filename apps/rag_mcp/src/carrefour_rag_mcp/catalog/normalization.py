"""Shared normalization rules for catalog labels and incoming queries."""

import unicodedata


def normalize_exam_name(value: str) -> str:
    """Fold case, accents, punctuation, and whitespace into a stable key."""
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_marks = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    alphanumeric_words = "".join(
        character if character.isalnum() else " " for character in without_marks
    )
    return " ".join(alphanumeric_words.split())
