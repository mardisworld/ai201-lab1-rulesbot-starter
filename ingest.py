import os
from config import DOCS_PATH


def load_documents():
    """Load all .txt rule documents from the docs folder."""
    documents = []
    for filename in sorted(os.listdir(DOCS_PATH)):
        if filename.endswith(".txt"):
            filepath = os.path.join(DOCS_PATH, filename)
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
            game_name = filename.replace(".txt", "").replace("_", " ").title()
            documents.append({
                "game": game_name,
                "filename": filename,
                "text": text,
            })
    print(f"Loaded {len(documents)} rule document(s): {[d['game'] for d in documents]}")
    return documents


def chunk_document(text, game_name):
    """
    Split a rule document into chunks ready for embedding.

    Strategy: section-based chunking with game/heading enrichment.

    The rule documents are written as sections — an ALL-CAPS heading line
    (e.g. "ROLLING A 7", "BUILDING") followed by one or more body paragraphs,
    until the next heading. A section is the natural semantic unit, so we cut
    on heading boundaries rather than at fixed character counts. This keeps a
    rule intact with its heading and on a single topic, which gives each chunk
    enough focused semantic signal to embed close to a matching question (e.g.
    the whole "ROLLING A 7" robber rule becomes one chunk) and far from
    unrelated rules in other games.

      - A new chunk starts at each ALL-CAPS heading line; the heading and all
        following body lines, up to the next heading, form one chunk.
      - min_length = 50: a section shorter than this (e.g. a lone title line)
        is merged forward into the next one rather than emitted as a noisy
        fragment.
      - Enrichment: each chunk's text is prefixed with "{game} — {heading}".
        Without this, only the OVERVIEW chunk contained the game name, so any
        query naming the game ("...in Pandemic") was pulled toward that generic
        overview, often outranking the section that actually answered it. With
        the name in *every* chunk the game stops being a discriminator, so the
        topic decides the ranking — this measurably lowered distances and
        pushed the overview out of the top results in testing.

    Returns a list of dicts, each with:
      - "text"     : the chunk text (str), prefixed with "{game} — {heading}"
      - "game"     : the game name, e.g. "Catan" (str)
      - "chunk_id" : a unique identifier, e.g. "catan_0", "catan_1" (str)
    """
    min_length = 50

    def is_heading(line):
        # Headings are short, all-caps lines (allowing digits/punctuation),
        # e.g. "ROLLING A 7" or "DEVELOPMENT CARDS".
        stripped = line.strip()
        return bool(stripped) and stripped.isupper() and len(stripped) < 50

    # Group lines into sections, breaking each time a heading line is seen.
    sections = []
    current = []
    for line in text.splitlines():
        # Skip the boilerplate document title (e.g. "RISK — OFFICIAL RULES
        # SUMMARY"). It carries no rule content, only duplicate game-name
        # signal that would turn the OVERVIEW chunk into a magnet for any
        # query naming the game.
        if "OFFICIAL RULES SUMMARY" in line.upper():
            continue
        if is_heading(line) and current:
            sections.append("\n".join(current).strip())
            current = []
        current.append(line)
    if current:
        sections.append("\n".join(current).strip())

    chunks = []
    prefix = game_name.lower().replace(" ", "_")
    counter = 0

    def enrich(section):
        # Prefix the chunk with "{game} — {heading}" so every chunk carries
        # the game name and its topic heading (see docstring).
        heading = section.splitlines()[0].strip()
        return f"{game_name} — {heading}\n{section}"

    # A section shorter than min_length is carried forward and prepended to
    # the next section so short headers/titles ride along with real content.
    carry = ""
    for section in sections:
        section = (carry + "\n\n" + section).strip() if carry else section
        if len(section) < min_length:
            carry = section
            continue
        carry = ""
        chunks.append({
            "text": enrich(section),
            "game": game_name,
            "chunk_id": f"{prefix}_{counter}",
        })
        counter += 1

    # If a trailing short section is still buffered, append it to the last
    # chunk (or emit it alone if there is no previous chunk).
    if carry:
        if chunks:
            chunks[-1]["text"] += "\n\n" + carry
        else:
            chunks.append({
                "text": enrich(carry),
                "game": game_name,
                "chunk_id": f"{prefix}_{counter}",
            })
    return chunks
