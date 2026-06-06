# Spec: `retrieve()`

**File:** `retriever.py`
**Status:** Spec incomplete — fill in all blank fields before implementing

---

## Purpose

Given a user's natural language query, find the most relevant chunks from the vector store using semantic similarity search. Return them ranked by relevance so that `generate_response()` can use them as context.

---

## Input / Output Contract

**Inputs:**

| Parameter | Type | Description |
|-----------|------|-------------|
| `query` | `str` | The user's natural language question |
| `n_results` | `int` | Maximum number of chunks to return (default: `N_RESULTS` from `config.py`) |

**Output:** `list[dict]`

Each dict in the returned list must contain exactly these keys:

| Key | Type | Description |
|-----|------|-------------|
| `"text"` | `str` | The chunk text |
| `"game"` | `str` | The game name this chunk came from |
| `"distance"` | `float` | Cosine distance score — lower means more similar to the query |

Results should be ordered from most to least relevant (lowest to highest distance). Returns an empty list `[]` if the collection contains no documents.

---

## Design Decisions

*Complete the fields below before writing any code. Use your AI tool in Plan or Ask mode to help you reason through what belongs here — but the decisions are yours.*

---

### Query approach

*Describe how you will use `_collection.query()` to find relevant chunks. What arguments will you pass, and why?*

```
I call _collection.query() with three arguments. query_texts=[query] passes the user's question as raw text so ChromaDB embeds it with the same embedding function used on the stored chunks — putting question and chunks in one comparable vector space. I wrap it in a list because query() supports batched queries; with a single query, my results live at index [0]. n_results=n_results sets top-k (default N_RESULTS), balancing recall against flooding the model with weakly-related context. include=["documents", "metadatas", "distances"] returns exactly the three fields my output contract needs: the text, the source game (from metadata), and the cosine distance for ranking — distances and metadatas must be requested explicitly. Results arrive sorted lowest-distance (most similar) first, so I preserve that order.


Include:  |	Needed for:                               |	Spec output key:
documents |	the actual chunk text to feed the model	  | "text"
metadatas |	which game it came from	                  | "game"
distances |	the relevance/similarity score	          | "distance"
Note: ids come back by default and they are not needed here, but distances and metadatas must be requested explicitly. Without distances, you can't report relevance or do any thresholding. Without metadatas, you can't tell Catan from Pandemic. As stated in the criteria, data from the wrong game is bad retrieval. 
```

---

### Return structure

*Sketch out what one item in your return list looks like as a concrete example. Where does each field come from in the query results?*

```
{"text": "When you roll a 7, the robber must be moved...", "game": "Catan", "distance": 0.14}
"text" comes from results["documents"][0][i] (the chunk string). "game" comes from results["metadatas"][0][i]["game"] — metadata is a dict, so I index the "game" key inside it. "distance" comes from results["distances"][0][i]. The [0] selects my single query's results; i walks the index-aligned inner lists, which are already ordered lowest-distance first. I build the list by zipping the three inner lists so each dict pulls from the same i.
```

---

### Handling the nested result structure

*`_collection.query()` returns nested lists. Describe what index you need to access to get the actual list of results for a single query, and why the nesting exists.*

```
You need index [0] on each list before iterating.


docs  = results["documents"][0]   # the inner list of actual documents
metas = results["metadatas"][0]
dists = results["distances"][0]

_collection.query() is designed to accept multiple queries in one call via query_texts. So every list it returns is organized as:


results["documents"][ which_query ][ which_result ]
                     └─ outer ─┘   └─── inner ───┘
Outer list = one entry per query you submitted.
Inner list = the n_results chunks for that one query, sorted closest-first.
Even when you send a single query, ChromaDB keeps the same uniform shape — it doesn't collapse the outer list. That consistency is what makes batching work: query #0's results are always at [0], query #1's at [1], and so on.

Why [0] specifically
I am calling it with query_texts=[query] — a list of exactly one query. So there's only one entry in the outer list, and it's at index [0]. That single [0] peels off the (length-1) query dimension and hands you the inner list of actual results to loop over.

Concretely, with the example from before:


results["distances"]        # [[0.14, 0.31, 0.82]]  ← outer: one query
results["distances"][0]     # [0.14, 0.31, 0.82]    ← inner: the results you want
results["distances"][0][0]  # 0.14                  ← first/closest result

_collection.query() returns doubly-nested lists shaped as results[key][query_index][result_index]. The outer list has one entry per query because query() supports batching multiple query_texts at once; the inner list holds the n_results chunks for that query, sorted lowest-distance first. Since I pass a single-element query_texts=[query], all my results live in the outer list's only entry — index [0]. So I access results["documents"][0], results["metadatas"][0], and results["distances"][0] to get the three index-aligned inner lists, then iterate those in parallel. The [0] strips off the query dimension; without it I'd be looping over queries (one item) instead of over results.
```

---

### Relevance threshold

*Will you filter out results above a certain distance score, or return all `n_results` regardless of how relevant they are? What are the tradeoffs of each approach?*

```
I will not hard-filter by distance in my initial implementation — I'll return all n_results, sorted closest-first, and let the LLM weigh the context. Rationale: a fixed threshold is dataset-dependent and risks discarding genuinely relevant chunks (false "not in the rules" answers), and per the spec's own guidance, wrong-game/high-distance results usually signal a chunking problem that a threshold would only mask. My plan is to first inspect real distance scores via my test query (Implementation Notes), confirm chunk quality, and only then consider a generous guard cutoff (e.g. drop distance > 0.8) to filter obvious junk while keeping k small enough to avoid flooding the model. Tradeoff acknowledged: returning all k means an occasional weakly-related chunk reaches the prompt, but that's safer than silently dropping a correct one.
```

---

### Edge cases

*How does your implementation behave when: (a) the collection is empty, (b) the query matches no chunks well, (c) the query matches chunks from multiple games?*

```
(a) The collection is empty
This is already handled at the top of your function (retriever.py:68-69):


if _collection.count() == 0:
    return []
So you short-circuit and return [] before ever calling query(). This matters because querying an empty collection is wasteful (and can behave oddly), and your output contract explicitly says "Returns an empty list [] if the collection contains no documents" (retrieve-spec.md:33). The caller (generate_response()) then sees no context and can tell the user the rules aren't loaded.

(b) The query matches no chunks well
Key insight: semantic search always returns something. ChromaDB has no concept of "no match" — it returns the k closest chunks even when the closest is barely related. So a nonsense query like "what's the weather today?" still comes back with k chunks, just at high distances (0.8–0.9+).

How your implementation behaves depends on the threshold decision you already made:

No threshold (your chosen approach): you return all k chunks with their honest high distances. The distance scores are your signal that these are weak — and you're deferring the judgment of "is this good enough" to the LLM and/or a later guard.
If you later add a guard cutoff: chunks above the cutoff get dropped, and if all of them exceed it, you return [] — letting the bot say "I don't know" rather than answering from junk.
Either way, the honest answer for the spec is: the function still returns results, but their high distances flag them as low-confidence — nothing crashes, and the distance is the diagnostic.

(c) The query matches chunks from multiple games
retrieve() does no game filtering — it searches the entire collection by pure semantic similarity. So a generic query like "how many players can play?" legitimately pulls chunks from Catan, Pandemic, and Monopoly, interleaved and sorted by distance.

This is correct, expected behavior, not a bug:

Each returned dict carries its own "game" field (from metadata), so downstream code can always tell which game each chunk came from.
A specific query ("what happens when you roll a 7?") naturally clusters results in one game because that content only embeds close to one game's rules.
A mixed result set on a specific query is the warning sign from your criteria — it usually means chunks are too small to carry enough semantic signal to distinguish games, not that the query logic is wrong.
(Optional note: ChromaDB does support a where={"game": ...} metadata filter, but this lab's retrieve() intentionally doesn't use it — the bot doesn't know which game the user means in advance, so filtering by game isn't appropriate here.)
```

---

## Implementation Notes

*Fill this in after implementing, before moving to Milestone 3.*

**Test query and top result returned:**

```
Query: What happens when you roll a 7?
Results:
0.466  Catan   'x, that hex produces no resources that turn, regardless of the number'
0.597  Risk    'd 2+ dice) the second-highest attacker die to the second-highest defen'
0.610  Risk    'ROLLING DICE\nThe attacker rolls up to 3 dice...'

Top result game: Catan
Distance score: 0.466
Does it make sense? Partially — right game, but it's a mid-word fragment
  ("x, that hex...") and results 2-3 are from the wrong game (Risk).

Rolling a 7 in Catan triggers the robber. Ideally the top result would be a Catan robber chunk at distance ~0.1–0.2. Instead:

Top result is mediocre (0.466), not great — and notice the text starts with 'x, that hex...'. That's a chunk cut mid-word ("...hex" had its start sliced off). It's a fragment, not a coherent rule.
Results 2 and 3 are the wrong game (Risk, ~0.6) — they matched on the word "roll"/"dice," not on the actual robber concept.
This is the textbook symptom from your spec's diagnostics (retrieve-spec.md:85, and the criteria you pasted earlier): wrong-game chunks at high distance + fragments = a chunking problem, not a retrieval bug. Your retrieve() is doing its job correctly — it's faithfully returning the closest chunks. The chunks themselves just don't carry enough semantic signal.

The root cause is in ingest.py:56 — the character-based chunker (text[start:end]) cuts at fixed 300-char boundaries, slicing mid-word and mid-sentence, which is why you see fragments like 'x, that hex...'.
```

**One thing about the query results that surprised you:**

```
[your answer here]
```
