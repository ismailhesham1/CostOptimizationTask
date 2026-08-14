#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Zero-cost gender lookup for EN->AR first names, to resolve gendered
prefixes (Dr./Prof./Eng.) without depending on the LLM's inferred gender.

Only ever consulted for first names written in Latin script (the en2ar
direction) -- see EXPERIMENT_LOG.md, "Gender-inference cost-reduction
workstream", Phase 1: ar2en never needs this, because AR_TO_EN_PREFIX
already disambiguates gender from the Arabic prefix word itself.

Two static tiers, hand-curated from general knowledge (not scraped from any
single external dataset, to sidestep a licensing review neither tier needs):

  Tier 1 -- common Latin-spelling variants of Arabic given names.
  Tier 2 -- common Western given names.

A third bucket, AMBIGUOUS, exists for names that are genuinely unisex or
that this curation isn't confident enough about to auto-resolve (nature/
virtue names like "River", "Sage", "Justice" are the recurring pattern --
see EXPERIMENT_LOG.md for the reasoning on each). These are listed
explicitly -- as a documented decision, not a silent gap -- and always
resolve to a miss, same as a name absent from every tier.

CONFIDENCE AND THE AUTO-RESOLVE THRESHOLD. Every entry carries a confidence
in [0, 1]. `lookup_gender()` only returns a usable answer at or above
AUTO_RESOLVE_THRESHOLD; anything below that (or explicitly AMBIGUOUS) comes
back as a miss, which the caller should treat exactly like "not in the
dictionary" -- fall through to the LLM. This is deliberate: the project's
standing rule is that a wrong answer is worse than a $0 miss (see
README.md's quality framing, and SUBMISSION.md's zero-hallucination
findings this project treats as its quality bar). Nothing in this module
should ever be the reason a customer sees the wrong gendered prefix.
"""
import re
import unicodedata

_WHITESPACE = re.compile(r"\s+")

AUTO_RESOLVE_THRESHOLD = 0.90


def norm_key(s):
    """Same normalisation as preprocess.py's norm_key / cache.json keys:
    NFC, whitespace-collapsed, casefolded. Duplicated here rather than
    imported to avoid a circular import with preprocess.py (which imports
    this module) -- the project already has three independent copies of
    this exact function (preprocess.py, score.py, experiments/pipeline/
    common.py), so a fourth is consistent with existing practice, not a
    new inconsistency."""
    text = unicodedata.normalize("NFC", s or "")
    return _WHITESPACE.sub(" ", text).strip().casefold()


# ---------------------------------------------------------------------------
# Tier 1: Arabic given names, common Latin signup spellings.
# Confidence 0.95 default -- these are conventional, low-ambiguity spellings
# of names with a fixed grammatical gender in Arabic (the language itself
# marks most of these unambiguously, unlike English nature/virtue names).
# ---------------------------------------------------------------------------
_TIER1_MALE = """
mohamed mohammed mohammad muhammad mohamad muhammed mohd
ahmed ahmad
ali aly
omar umar omer
hassan hasan
hussein husain hussain housein
khalid khaled
abdullah abdallah abdulla abdalla
abdulrahman abdelrahman abdurrahman abdrahman
abdulaziz abdelaziz
ibrahim ebrahim
youssef yousef yusuf yousif yousuf
ismail ismael
mahmoud mahmud mahmood
mostafa mustafa moustafa
tariq tarek tarik
waleed walid
kareem karim
jamal gamal
kamal
faisal faysal
saeed said sayed
sami samy
samir sameer
salem salim saleem
sultan
sharif shareef
nasser nasir naser
nabil
majid majeed
marwan
rami ramy
rashid rasheed
zaid zayd zayed
ziad zyad
yasser yaser
wael wail
ayman
ammar amar
anas
adel adil aadel
emad imad
bassam
bilal belal
fadi fady
hisham
jaber jabir
khalil khaleel
mazen
nayef naif nayif
osama usama
qasim qassim kasim
sherif cherif
talal
yazan
hamza hamzah
hussam housam
iyad eyad
mansour mansur
raed raied rayed
sameh
tamer tamir
waseem wasim
younes yunus
karim
khalifa
rida reda
loay louai
malek malik
zaki zakey
naseem nassim
adnan
anwar
fouad fuad
ghassan
hazem hazim
karam
majd
murad mourad
nael nail
rafik rafiq
saad sa'd
salman
tamim
walaa
yaseen yasin
zakaria zakariya
""".split()

_TIER1_FEMALE = """
fatima fatma fatimah fatema
aisha aysha ayesha aicha
khadija khadijah khadeja
zainab zaynab zeinab zenab
maryam mariam meriam
layla laila leila leyla
salma
rania rana raniah
dalia dalya
dina deena
hala
hanan
huda hoda
iman imaan
mona muna
nadia nadya nadja
noura nourah
reem riam rim
sahar
samira sameera
sara sarah
wafa wafaa
yasmin yasmine jasmine jasmin
abeer abir
amal
amira ameera emira
asma asmaa
bushra
farah
ghada
ghina
hadeel hadil
hind
jana jenna
lina leena
lubna
maha
malak
manal
marwa
nawal
nesrine nesreen nisreen
rawan
rima reema
roula rula
shaimaa shayma
shurouq shorouk
suha
yara
dania daniah
dima deema
ola olla
rana
salwa
samah
soha
souad suad
hebba heba
inas enas
lamia lamya
mervat mirvat
nagwa
nahed nahid
nawara
rasha
safa
sanaa sana
sawsan
seham siham
suzan susan
warda
""".split()

# ---------------------------------------------------------------------------
# Tier 2: general Western given names. Hand-curated common set -- not
# exhaustive, and deliberately excludes the nature/virtue/unisex cluster
# (handled below in AMBIGUOUS instead of guessed here).
# ---------------------------------------------------------------------------
_TIER2_MALE = """
james john robert michael william david richard joseph thomas charles
christopher daniel matthew anthony mark donald steven andrew paul joshua
kenneth kevin brian george edward ronald timothy jason jeffrey ryan jacob
gary nicholas eric jonathan stephen larry justin scott brandon benjamin
samuel frank gregory raymond alexander patrick jack dennis jerry tyler
aaron jose henry adam douglas nathan peter zachary walter kyle harold carl
jeremy keith roger gerald ethan arthur terry christian sean lawrence
austin joe noah jesse albert bryan billy bruce willie dylan alan
ralph gabriel roy juan wayne eugene logan randy louis russell vincent
philip bobby johnny bradley leonard oscar victor felix leo max simon
julian dominic sebastian theodore frederick francis harry howard martin
nicolas oliver owen preston quentin xavier caleb elijah isaac isaiah levi
lucas mason miles nolan tobias wesley marcus nathaniel
drake dale earl hunter heath chase reed fox king noble prince
""".split()

_TIER2_FEMALE = """
mary patricia jennifer linda elizabeth barbara susan jessica sarah karen
lisa nancy betty margaret sandra ashley kimberly emily donna michelle
dorothy carol amanda melissa deborah stephanie rebecca sharon laura
cynthia kathleen amy angela shirley anna brenda pamela emma nicole helen
samantha katherine christine debra rachel catherine carolyn janet ruth
maria heather diane virginia julie joyce victoria olivia kelly christina
lauren joan evelyn judith megan andrea cheryl hannah jacqueline martha
gloria teresa janice marie julia heidi grace judy theresa madison beverly
denise marilyn danielle abigail brittany diana natalie sophia alexis lori
kayla jane charlotte isabella chloe alice penelope eleanor gabrielle
josephine beatrice cecilia genevieve rosalind ruby daisy lily iris ivy
hazel violet rose pearl hope joy serenity autumn faith summer april june
paige mia ella scarlett audrey claire vivian nora stella willow luna
amber amelia melody
""".split()

# ---------------------------------------------------------------------------
# Explicitly ambiguous / unisex / low-confidence: recorded on purpose so a
# future maintainer (or Phase 4 fuzzy matching) doesn't accidentally treat
# "not resolved" as "not considered". Always falls through to the LLM.
# ---------------------------------------------------------------------------
AMBIGUOUS = {
    "river", "sage", "sky", "skye", "rain", "robin", "justice", "liberty",
    "brook", "star", "phoenix", "jordan", "taylor", "morgan", "casey",
    "jamie", "peyton", "rowan", "avery", "nour", "noor", "jihad", "angel",
}


def _build_tier(male_words, female_words, tier, confidence):
    table = {}
    for w in male_words:
        existing = table.get(w)
        if existing and existing[0] != "M":
            raise ValueError(f"{tier}: {w!r} listed as both M and F")
        table[w] = ("M", confidence, tier)
    for w in female_words:
        existing = table.get(w)
        if existing and existing[0] != "F":
            raise ValueError(f"{tier}: {w!r} listed as both M and F")
        table[w] = ("F", confidence, tier)
    return table


_TIER1 = _build_tier(_TIER1_MALE, _TIER1_FEMALE, "tier1_arabic", 0.95)
_TIER2 = _build_tier(_TIER2_MALE, _TIER2_FEMALE, "tier2_western", 0.90)

# A name legitimately common to both tiers (e.g. "Sarah") is fine as long as
# both tiers agree on gender -- tier1 wins the tier label in that case, per
# the plan's "prioritize coverage here" call for tier1. Actual disagreement
# (same spelling, different gender across tiers) is a real curation bug and
# still fails loudly.
_conflicts = {
    k for k in (set(_TIER1) & set(_TIER2)) if _TIER1[k][0] != _TIER2[k][0]
}
if _conflicts:
    raise ValueError(f"tier1/tier2 gender disagreement: {sorted(_conflicts)}")

GENDER_TABLE = {**_TIER2, **_TIER1}  # tier1 applied last, wins ties


def lookup_gender(name):
    """Returns (gender, confidence, tier) for a first name, using the same
    normalisation as cache.json. gender is 'M' or 'F' only when confidence
    >= AUTO_RESOLVE_THRESHOLD; otherwise returns (None, 0.0, None) -- a
    miss, to be treated identically to "not in the dictionary" by callers.
    """
    k = norm_key(name)
    if k in AMBIGUOUS:
        return None, 0.0, "ambiguous"
    hit = GENDER_TABLE.get(k)
    if hit is None:
        return None, 0.0, None
    gender, confidence, tier = hit
    if confidence < AUTO_RESOLVE_THRESHOLD:
        return None, confidence, tier
    return gender, confidence, tier


if __name__ == "__main__":
    # Round-trip sanity check: every curated name resolves to itself.
    failures = []
    for k, (g, conf, tier) in GENDER_TABLE.items():
        got_g, got_conf, got_tier = lookup_gender(k)
        if conf >= AUTO_RESOLVE_THRESHOLD and (got_g != g or got_tier != tier):
            failures.append((k, g, got_g))
    for k in AMBIGUOUS:
        g, conf, tier = lookup_gender(k)
        if g is not None:
            failures.append((k, "expected-miss", g))
    if failures:
        print(f"FAIL: {len(failures)} round-trip mismatch(es):")
        for f in failures[:20]:
            print(" ", f)
        raise SystemExit(1)
    print(f"OK: {len(GENDER_TABLE)} entries "
          f"({len(_TIER1)} tier1 + {len(_TIER2)} tier2), "
          f"{len(AMBIGUOUS)} explicit ambiguous, all round-trip clean.")
