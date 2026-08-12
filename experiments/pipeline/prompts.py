# -*- coding: utf-8 -*-
"""Prompt construction for the bake-off. Two versions, deliberately:

  v1 - naive: measures raw model capability, no convention pinning.
  v2 - glossary + style rules: measures what's actually achievable.

Compare both across all three models. If the spread between models shrinks
from v1 to v2, that demonstrates prompt engineering substitutes for model
spend -- log it, it's one of the stronger findings available here.
"""

STYLE_RULES = """\
You are transliterating personal names between English and Arabic for a \
customer-facing greeting. Precision matters: a wrong letter is a wrong name.

Rules:
- Preserve Arabic orthography exactly: keep hamza forms (أ إ آ ء ؤ ئ) and \
ta marbuta (ة) where they belong. Do not simplify or drop them.
- Render the Arabic definite article "ال" as "Al-" (capital A, hyphen, no \
space) when transliterating to English, e.g. البلوي -> Al-Balawi.
- Preserve name particles as separate words: "bin", "ibn", "Abu" stay \
lowercase/capitalised as conventionally written and are not merged into \
the following word.
- For long Arabic vowel sounds, prefer the double-letter English spelling \
over the single-letter one: "Kareem" not "Karim", "Waleed" not "Walid", \
"Al-Ameen" not "Al-Amin", "Jameel" not "Jamil".
- A name-final Arabic ة (ta marbuta) transliterates to a plain final "-a", \
never "-ah": "Hamza" not "Hamzah", "Sara" not "Sarah", "Baraka" not "Barakah".
- Compound names stay one unbroken word, never split with a space at the \
join: "Abdullah" not "Abd Allah", "Abdulrahman" not "Abd Al-Rahman", \
"Nasrallah" not "Nasr Allah", "Lockwood" -> "لوكوود" not "لوك وود".
- When a foreign name starts with a long open "aa" sound, render it with \
آ (alif+madda), not a plain أ: "Amber" -> "آمبر", "Iris" -> "آيريس".
- Output only the transliteration/translation itself: no explanation, no \
transliteration marks, no alternate spellings.
- If a name has no accepted rendering in the target script (e.g. it is \
already a single universal word), return your best-supported transliteration \
-- never leave the field blank.
"""

GLOSSARY_PREAMBLE = """\
Known accepted spellings already in use for this dataset (prefer these \
exactly if a name matches one, instead of inventing a new spelling):
{terms}
"""

RESPONSE_SCHEMA = {
    "type": "object",
    "properties": {
        "results": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "integer"},
                    "text": {"type": "string"},
                    "gender": {
                        "type": "string",
                        "description": (
                            "Only for first names: the person's apparent "
                            "gender inferred from the name, as 'M' or 'F'. "
                            "Leave as an empty string for last_name/prefix "
                            "entries or when gender cannot be inferred."
                        ),
                    },
                },
                "required": ["id", "text"],
            },
        },
    },
    "required": ["results"],
}


def build_prompt(direction, items, glossary_terms=None, use_glossary=False):
    """items: list of (id:int, token:str, slot:str) where slot is
    'first_name' | 'last_name' | 'prefix'. Returns the full user prompt text.
    """
    src_lang = "Arabic" if direction == "ar2en" else "English"
    dst_lang = "English" if direction == "ar2en" else "Arabic"

    parts = [STYLE_RULES]
    if use_glossary and glossary_terms:
        parts.append(GLOSSARY_PREAMBLE.format(terms=glossary_terms))

    parts.append(
        f"Translate each of the following {src_lang} name fragments into "
        f"{dst_lang}. Return JSON matching the schema, one result per input "
        f"id, in any order. For entries whose slot is 'first_name', also "
        f"infer gender (M/F) from the name; leave gender empty for "
        f"last_name and prefix entries.\n"
    )
    lines = [f'{{"id": {i}, "slot": "{slot}", "text": "{tok}"}}'
              for i, tok, slot in items]
    parts.append("[\n  " + ",\n  ".join(lines) + "\n]")

    return "\n".join(parts)
