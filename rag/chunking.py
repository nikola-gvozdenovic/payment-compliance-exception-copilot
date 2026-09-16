"""Parses a corpus markdown file and splits it into citable chunks.

A document is split by its top-level `##` sections when it has 2 or more of them;
a document with 0 or 1 `##` sections (e.g. every sanctions_mock entry, which uses
bold field labels instead of headers) is treated as a single chunk. Every chunk's
text is prefixed with the document's `# ` title so it reads sensibly on its own,
since a retrieved chunk has no other document context around it.
"""

import datetime
import re
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel

_H1_PATTERN = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_H2_PATTERN = re.compile(r"^##\s+.+$", re.MULTILINE)


class Chunk(BaseModel):
    """One citable piece of a corpus document, ready to embed and store."""

    chunk_id: str
    text: str
    metadata: dict[str, Any]


def _normalize_metadata_value(value: Any) -> Any:
    """Chroma's metadata validation rejects two shapes YAML naturally produces:

    - `datetime.date`/`datetime.datetime` (from an unquoted date like `2026-01-10`)
      -- only str/int/float/bool/list/None are allowed, so stringify it.
    - an *empty* list (e.g. `supports_flag_reason: []`) -- Chroma accepts a
      non-empty list but raises ValueError on an empty one, so normalize to None.

    Everything else passes through as-is.
    """
    if isinstance(value, datetime.date | datetime.datetime):
        return value.isoformat()
    if isinstance(value, list) and len(value) == 0:
        return None
    return value


def parse_document(path: Path) -> tuple[dict[str, Any], str, str]:
    """Split a corpus markdown file into (frontmatter, title, body-without-the-title-line).

    The `# ` title line itself is removed from the returned body (not just skipped
    over) -- every chunk gets `title` prepended explicitly (see chunk_document), so
    leaving the raw title line in body would duplicate it in every chunk's text.
    """
    _, frontmatter_raw, body = path.read_text().split("---", 2)
    frontmatter = yaml.safe_load(frontmatter_raw)
    frontmatter = {k: _normalize_metadata_value(v) for k, v in frontmatter.items()}
    body = body.strip()
    title_match = _H1_PATTERN.search(body)
    if title_match:
        title = title_match.group(1).strip()
        body = (body[: title_match.start()] + body[title_match.end() :]).strip()
    else:
        title = frontmatter["doc_id"]
    return frontmatter, title, body


def chunk_document(doc_id: str, title: str, body: str, metadata: dict[str, Any]) -> list[Chunk]:
    """Split by top-level ## sections; whole body as one chunk if fewer than 2 sections.

    Any text before the first ## heading (the fictional-content watermark banner,
    plus any intro prose) is folded into chunk 0 rather than discarded -- it would
    otherwise silently vanish from every chunk of a multi-section document.
    """
    matches = list(_H2_PATTERN.finditer(body))
    if len(matches) < 2:
        return [
            Chunk(
                chunk_id=f"{doc_id}::chunk-0",
                text=f"# {title}\n\n{body}",
                metadata={**metadata, "chunk_index": 0},
            )
        ]

    intro_text = body[: matches[0].start()].strip()
    chunks = []
    for i, match in enumerate(matches):
        start = match.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        section_text = body[start:end].strip()
        if i == 0 and intro_text:
            section_text = f"{intro_text}\n\n{section_text}"
        chunks.append(
            Chunk(
                chunk_id=f"{doc_id}::chunk-{i}",
                text=f"# {title}\n\n{section_text}",
                metadata={**metadata, "chunk_index": i},
            )
        )
    return chunks
