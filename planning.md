# RulesBot — Planning Doc

Use this file to record your design decisions as you work through the lab.
There are no wrong answers — write enough that you could explain your reasoning to another group.

---

## Chunking Strategy

**Chunk size:**
Variable — one chunk per document *section*, not a fixed character count.
Sections run ~200–650 characters. We started with a fixed 300-char sliding
window but it cut mid-word/mid-sentence, producing fragments that didn't embed
meaningfully. Section boundaries (the ALL-CAPS headings) are the natural unit.

**Overlap:**
None. The original sliding window used 50-char overlap to avoid splitting a
rule across a boundary. Section-based chunking makes overlap unnecessary —
each section is already a complete, self-contained rule, so there's no
boundary to bridge.

**Why this strategy fits rule book text:**
These rulebooks are written as labeled sections (OVERVIEW, SETUP, ROLLING A 7,
TRADING, ...), each covering one topic. Cutting on those headings keeps every
rule intact and on a single topic, so each chunk carries enough focused
semantic signal to (a) match a relevant question and (b) contain the *complete*
answer. We verified end-to-end that this matters: a single-sentence chunker had
a lower distance on "roll a 7" but the LLM gave an incomplete answer (it
dropped the discard/robber/steal rules) — the full section gave the complete
one. Two refinements on top: each chunk is prefixed with "{game} — {heading}"
so the game name appears in every chunk (stops the generic OVERVIEW chunk from
being a magnet for any query naming the game), and the boilerplate title line
("X — OFFICIAL RULES SUMMARY") is stripped as noise.

---

## Retrieval Observations

After implementing retrieval, try these test queries and record what comes back:

| Query | Top result game | Does it make sense? |
|-------|----------------|---------------------|
| "How do you win?" | Catan (0.471) | Yes — but it's a tie: Catan/Monopoly/Uno WINNING sections all came back at ~0.47. No game was named, so returning multiple games' win conditions is correct. |
| "What happens when you roll a 7?" | Catan (0.441) | Yes — top result is Catan's ROLLING A 7 (robber) section. The other two are Risk dice rules at higher distance (0.57+), correctly behind. |
| "Can two players share a route?" | Ticket To Ride (0.450) | Yes — all top-3 are Ticket to Ride route/claiming sections. Perfect game disambiguation even though the query never names the game. |

**Anything surprising?**
Two things. (1) Semantic search *always* returns k results — there's no "no
match." A game-less or out-of-scope query still returns chunks; the distance
score is what flags them as weak (in-scope answers landed ~0.23–0.47, clearly
out-of-scope ones ~0.6+). (2) Lower distance does not mean a better answer.
Single-sentence chunks scored lower distances but produced incomplete answers
because the rest of the rule lived in other chunks — the metric is a proxy,
not the goal.

---

## Response Quality

After implementing generation, try 2–3 questions and assess the answers:

| Query | Answer accurate? | Properly grounded? | Cited the right game? |
|-------|-----------------|-------------------|----------------------|
| "How do you get out of Jail in Monopoly?" | Yes — $50 fine within 3 turns / Get Out of Jail Free card / roll doubles (verified against monopoly.txt) | Yes | Yes — [Source: Monopoly — JAIL] |
| "Can I trade resources with the bank?" (no game named) | Yes — 4-for-1 bank trade, harbor trades reduce ratio | Yes — ignored the Monopoly TRADING chunk that was also retrieved | Yes — [Source: Catan — TRADING] |
| "Exact point value of Free Parking?" (not in docs) | Correctly said the value "is not specified" instead of guessing | Yes | Yes — [Source: Monopoly — FREE PARKING] |

**What would you change about the prompt to improve grounding?**
We iterated on exactly this. Two changes mattered most: (1) write the
instruction as a *prohibited behavior* ("do not draw on outside knowledge / do
not fill gaps") rather than a desired outcome ("be accurate") — the former
gives the model nothing to sidestep. (2) Add concrete prohibited-behavior
*examples*. On the first run the model answered the Free Parking trap with
"...which implies the value is $0" — a subtle inference from silence. Adding
an explicit example to the no-inference rule ("do not convert 'no effect' into
a value") fixed it. Also added "ignore irrelevant sources" so multi-game
context doesn't bleed, and baked in the self-check: "could this sentence have
come from anywhere other than the provided text? If yes, delete it."

