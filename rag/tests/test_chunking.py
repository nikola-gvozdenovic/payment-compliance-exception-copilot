from rag.chunking import chunk_document, parse_document

_FRONTMATTER = """
doc_id: TEST-0001
doc_type: policy
version: "1.0"
date: 2026-01-10
fictional: true
supports_flag_reason: [timeout]
"""


def _write_doc(tmp_path, body: str):
    path = tmp_path / "TEST-0001.md"
    path.write_text(f"---{_FRONTMATTER}---\n\n{body}\n")
    return path


def test_parse_document_extracts_frontmatter_and_title(tmp_path):
    path = _write_doc(tmp_path, "**Watermark**\n\n# Test Document Title\n\nSome intro text.")

    frontmatter, title, body = parse_document(path)

    assert frontmatter["doc_id"] == "TEST-0001"
    assert frontmatter["doc_type"] == "policy"
    assert title == "Test Document Title"
    assert "Some intro text." in body


def test_parse_document_normalizes_date_and_empty_list(tmp_path):
    path = _write_doc(tmp_path, "# Title\n\nBody.")

    frontmatter, _, _ = parse_document(path)

    assert frontmatter["date"] == "2026-01-10"
    assert isinstance(frontmatter["date"], str)


def test_chunk_document_splits_by_h2_when_two_or_more_sections(tmp_path):
    body = "# Title\n\n## Rule\nRule text.\n\n## Rationale\nRationale text.\n\n## Enforcement\nEnforcement text."
    path = _write_doc(tmp_path, body)
    frontmatter, title, parsed_body = parse_document(path)

    chunks = chunk_document(frontmatter["doc_id"], title, parsed_body, frontmatter)

    assert [c.chunk_id for c in chunks] == [
        "TEST-0001::chunk-0",
        "TEST-0001::chunk-1",
        "TEST-0001::chunk-2",
    ]
    assert all(c.text.startswith(f"# {title}") for c in chunks)
    assert "Rule text." in chunks[0].text
    assert "Rationale text." in chunks[1].text
    assert "Enforcement text." in chunks[2].text


def test_chunk_document_single_chunk_when_no_sections(tmp_path):
    body = "# Title\n\n**Entity:** Some Company\n**Entity type:** Company\n"
    path = _write_doc(tmp_path, body)
    frontmatter, title, parsed_body = parse_document(path)

    chunks = chunk_document(frontmatter["doc_id"], title, parsed_body, frontmatter)

    assert len(chunks) == 1
    assert chunks[0].chunk_id == "TEST-0001::chunk-0"


def test_chunk_document_single_chunk_when_exactly_one_section(tmp_path):
    body = "# Title\n\n## Rule\nOnly one section here."
    path = _write_doc(tmp_path, body)
    frontmatter, title, parsed_body = parse_document(path)

    chunks = chunk_document(frontmatter["doc_id"], title, parsed_body, frontmatter)

    assert len(chunks) == 1


def test_chunk_metadata_includes_frontmatter_and_chunk_index(tmp_path):
    body = "# Title\n\n## A\nText A.\n\n## B\nText B."
    path = _write_doc(tmp_path, body)
    frontmatter, title, parsed_body = parse_document(path)

    chunks = chunk_document(frontmatter["doc_id"], title, parsed_body, frontmatter)

    assert chunks[0].metadata["doc_id"] == "TEST-0001"
    assert chunks[0].metadata["doc_type"] == "policy"
    assert chunks[0].metadata["chunk_index"] == 0
    assert chunks[1].metadata["chunk_index"] == 1


def test_chunk_metadata_normalizes_empty_list_to_none(tmp_path):
    path = tmp_path / "TEST-0002.md"
    path.write_text(
        "---\n"
        "doc_id: TEST-0002\n"
        "doc_type: jurisdiction_rule\n"
        'version: "1.0"\n'
        "date: 2026-01-10\n"
        "fictional: true\n"
        "supports_flag_reason: []\n"
        "---\n\n# Title\n\nBody with no sections.\n"
    )
    frontmatter, title, parsed_body = parse_document(path)
    assert frontmatter["supports_flag_reason"] is None  # normalized by parse_document itself

    chunks = chunk_document(frontmatter["doc_id"], title, parsed_body, frontmatter)

    assert chunks[0].metadata["supports_flag_reason"] is None
