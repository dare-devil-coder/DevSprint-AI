import sys
import pytest
import main

# Acceptance: Celsius to Fahrenheit conversion
@pytest.mark.parametrize("celsius,expected",[(0,"32.0"),(100,"212.0"),(-40,"-40.0"),(37,"98.6"),(1000000,"1800032.0")])
def test_celsius_to_fahrenheit_conversion_valid_input(monkeypatch, capsys, celsius: float, expected: str) -> None:
    # Acceptance: Celsius to Fahrenheit conversion
    monkeypatch.setattr(sys, "argv", ["prog", str(celsius)])
    main.main()
    captured = capsys.readouterr()
    assert captured.out.strip() == expected

# Acceptance: Graceful handling of non‑numeric input
def test_graceful_handling_of_non_numeric_input(monkeypatch, capsys) -> None:
    # Acceptance: Graceful handling of non‑numeric input
    monkeypatch.setattr(sys, "argv", ["prog", "abc"])
    with pytest.raises(SystemExit) as excinfo:
        main.main()
    captured = capsys.readouterr()
    assert "invalid float value" in captured.err
    assert excinfo.value.code == 2