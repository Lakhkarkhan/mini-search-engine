from minisearch.query import parse_query


def test_plain_terms_are_optional():
    q = parse_query("python tutorial")
    assert q.should == ["python", "tutorial"]
    assert not q.must and not q.must_not


def test_required_and_excluded_terms():
    q = parse_query("+python -java tutorial")
    assert q.must == ["python"]
    assert q.must_not == ["java"]
    assert q.should == ["tutorial"]


def test_phrase_offsets_are_relative_to_first_term():
    q = parse_query('"state of the art"')
    assert q.phrases == [[("state", 0), ("art", 3)]]


def test_excluded_phrase():
    q = parse_query('cats -"machine learning"')
    assert q.should == ["cat"]
    assert q.not_phrases == [[("machine", 0), ("learn", 1)]]


def test_stopword_only_query_is_empty():
    assert parse_query("the of and").is_empty
    assert parse_query("").is_empty


def test_scoring_terms_are_unique_and_include_phrases():
    q = parse_query('python +python "python tricks"')
    assert q.scoring_terms == ["python", "trick"]


def test_unbalanced_quote_does_not_crash():
    q = parse_query('"unclosed phrase')
    assert q.scoring_terms
