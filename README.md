# The Nimbus Retail Name Problem

**A two-day research task.**

---

## Monday, 09:14

You have been at Nimbus Retail for three weeks. Nimbus sells household goods
across a dozen markets, and about a year ago the company decided that every
customer should be spoken to in their own language — not just the interface,
but the little things. The greeting on the receipt. The subject line. The
first word of the welcome email.

That decision produced **Welcome Home**, the loyalty programme Nimbus launched
last quarter. It runs in two languages, English and Arabic, and every message
it sends opens with the customer's own name, correctly written in the language
they chose. `Ahmed Al-Rashid` if they read in English. `أحمد الراشد` if they
read in Arabic. Marketing tested it against a generic greeting and the
personalised version won by a margin large enough that nobody argues about it
any more.

The catch is that customers sign up in one language and are perfectly happy to
receive campaigns in the other, and a lot of them do both. So every new sign-up
needs its name rendered in the language it wasn't submitted in, and Nimbus does
that with the Gemini API.

Sign-ups arrive at roughly **one per second**, around the clock. That is about
**86,400 new names every day**, and the number has been trending up.

This morning, a message from Layla in Finance landed in your team's channel:

> Hi — we're doing the quarterly infrastructure review and the Gemini line item
> for Welcome Home came back much higher than anything we modelled. I don't
> think anyone's done anything wrong, I just don't think anyone's looked at it
> since launch. Before I escalate this, can someone take a proper look at
> whether we're doing it the cheap way or the expensive way?

Your team lead forwards it to you with three words: **"You've got Wednesday."**

---

## What Welcome Home does today

The service that handles this was written during the launch sprint and has not
been touched since. It works like this:

- A sign-up arrives.
- The service immediately sends one request to the Gemini API containing that
  one name.
- The model used is `gemini-2.5-pro`.
- The prompt asks, in plain English, for the name in the other language, and
  the reply comes back as free text, which the service parses.
- The result is written to the customer record.

Nobody claims this is good. It is simply what got written in the week before
launch, and it has been correct enough that no one revisited it. Reproducing
what it costs per thousand names is your starting measurement, not something to
take on faith — measure it yourself.

---

## The actual question

**What is the cheapest way to run this that Marketing would still accept?**

That is the whole assignment. It is deliberately not "make it cheaper by 40%",
because nobody knows yet what the floor is or what it costs in quality to get
there. Your job is to find out, and to come back with a number and a
recommendation you can defend.

Two things you should know, because they are real constraints and not hints:

**Latency.** Welcome Home does not send anything to a customer immediately.
Messages go out on a scheduled cycle, and the campaign team has confirmed that
a name may take **up to 30 hours** from sign-up to being ready without
affecting a single send. Anything faster is not worth paying for. Anything
slower breaks the campaign.

**Quality.** There is no fixed threshold handed down from above. Marketing's
position is that a customer should not see their own name written wrongly, and
they will accept the cheapest option that clears that bar. Deciding where that
bar sits — and defending it with evidence — is part of what you are being asked
to do.

---

## What you have been given

```
├── README.md              this file
├── SUBMISSION.md          the template you fill in and hand back
├── score.py               the validator
└── data/
    ├── names_input.csv    1,200 sign-ups
    └── gold.csv           the reference answers for those 1,200
```

### `data/names_input.csv`

A sample of 1,200 records taken from a single day of real sign-up traffic
(2 March), with the personal data replaced. One row per sign-up.

| column | meaning |
| --- | --- |
| `record_id` | unique id for the sign-up, `R000001` … `R001200` |
| `submitted_at` | when the sign-up arrived, UTC |
| `prefix` | title or honorific. Often empty. |
| `first_name` | given name |
| `last_name` | family name, including any particle (`Al-`, `bin`, `Abu`, `van der`) |

The name is already split into its parts for you, and the parts are clean:
whatever is in `first_name` really is the given name, whatever is in
`last_name` really is the family name, and the particles and honorifics are
already formatted consistently. Capitalisation is preserved exactly as the
customer typed it at sign-up.

### `data/gold.csv`

The reference translation for every one of the 1,200 records: `record_id`,
`prefix`, `first_name`, `last_name`, in the target language.

---

## How you are scored

Produce a UTF-8 CSV with a header row containing at least these four columns:

```
record_id,prefix,first_name,last_name
```

one row per `record_id`, holding your target-language values. Extra columns are
ignored and column order does not matter. Then:

```bash
python3 score.py my_output.csv
```

It prints per-field and whole-record accuracy and writes `failures.csv`
listing every field that did not match, with the expected and received values
side by side.

**Exactly how a field is compared.** Both sides are Unicode-NFC-normalised,
stripped of leading and trailing whitespace, have internal whitespace runs
collapsed to a single space, and are casefolded — so capitalisation never
counts against you. The two strings are then compared for plain equality.
There is no fuzzy matching and no list of alternative accepted spellings:
`gold.csv` holds exactly one form per field. `score.py` is short and you are
expected to read it.

---

## Rules

1. **`gold.csv` is for measuring, never for translating.** Your pipeline must
   not read it, directly or indirectly. We will re-run your code against a
   different set of names it has never seen, and it is expected to work.
2. **Track what you spend.** Every experiment's cost is part of your findings,
   including the ones that didn't work out.
3. **Your recommendation must survive 86,400 names a day**, not just the 1,200
   in the sample. Say so explicitly if something in your approach would not.
4. **Use whatever tools you like** — any language, any libraries, any AI
   assistance. Only the reasoning and the numbers are graded.

---

## API access

> **[TO BE COMPLETED BEFORE THIS TASK IS HANDED OUT]**
>
> - API key / project: `________`
> - Spend ceiling for the two days: `________`
> - Where to log your spend: `________`
>
> If you are close to the ceiling, stop and ask before continuing. Running out
> of budget on Wednesday morning is a much worse outcome than running one
> experiment fewer.

---

## What to hand back, by end of Wednesday

Fill in `SUBMISSION.md` and hand it back together with your code. Then be ready
to walk your team lead through it in about ten minutes.

The thing being judged is not how low a number you reach. It is whether you can
show *why* it is that number, what it cost in quality to get there, and what
you would have done next.

Good luck.
