

def test_thousands_separators_are_not_read_as_decimals():
    from backend.rules import parse_measurement

    for text, mm in [("1 200 mm", 1200), ("1 200 mm", 1200), ("1,200 mm", 1200), ("1 600 mm", 1600),
                     ("12,5 mm", 12.5), ("1200 mm", 1200), ("1,2 m", 1200), ("Deck 5 800 mm", 800), ("clear width of 1 000 mm", 1000)]:
        assert parse_measurement(text, "length").value == mm, text
