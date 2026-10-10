# celsius_to_fahrenheit

## What it does

A CLI tool that converts temperature from Celsius to Fahrenheit.

## How to install

Use Python 3.10 or newer. Install pytest to run the tests: python -m pip install pytest.

## How to run

Run python main.py --help for supported arguments, or python main.py to start with its default behavior.

## How to run tests

Run python -m pytest -q test_main.py.

## Features

- Celsius to Fahrenheit conversion
- Graceful handling of non‑numeric input

## Known limitations

- Invalid or missing command‑line arguments may cause unhandled exceptions
- Floating‑point rounding errors could affect precision of the result
- Dependence on argparse limits flexibility for future UI extensions
