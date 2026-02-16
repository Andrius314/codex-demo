from app import greet


def test_greet_contains_name():
    result = greet("Nerijus")
    assert "Nerijus" in result


def test_greet_raises_on_empty():
    try:
        greet("   ")
        raise AssertionError("Expected ValueError")
    except ValueError:
        pass
