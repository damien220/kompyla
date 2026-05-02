from kompyla.filter.dedup import Deduplicator, _content_hash


def test_exact_duplicate_detected():
    d = Deduplicator()
    text = "The quick brown fox jumps over the lazy dog."
    assert d.is_duplicate(text) is False
    d.add(text)
    assert d.is_duplicate(text) is True


def test_normalized_whitespace_is_dup():
    d = Deduplicator()
    a = "Hello   world\nfoo bar"
    b = "hello world foo bar"
    d.add(a)
    assert d.is_duplicate(b) is True


def test_near_duplicate_via_minhash():
    d = Deduplicator(threshold=0.7)
    base = " ".join(f"word{i}" for i in range(200))
    near = base + " extra word"
    d.add(base)
    assert d.is_duplicate(near) is True


def test_distinct_documents_not_duplicate():
    d = Deduplicator()
    d.add("Cats are mammals that purr and chase mice around the house.")
    assert d.is_duplicate("Quantum chromodynamics governs strong nuclear force.") is False


def test_content_hash_is_deterministic():
    assert _content_hash("hello world") == _content_hash("HELLO   WORLD")


def test_register_hash_seeds_dedup():
    text = "Already known content."
    d = Deduplicator()
    d.register_hash(_content_hash(text))
    assert d.is_duplicate(text) is True
