import argparse
import sys

def celsius_to_fahrenheit(celsius: float) -> float:
    """Convert Celsius to Fahrenheit.

    Args:
        celsius: Temperature in Celsius.

    Returns:
        Temperature in Fahrenheit.
    """
    return (celsius * 9 / 5) + 32

def main() -> None:
    """Main entry point for the CLI."""
    parser = argparse.ArgumentParser(
        description="Convert temperature from Celsius to Fahrenheit."
    )
    parser.add_argument(
        "celsius",
        type=float,
        help="Temperature in Celsius"
    )

    try:
        args = parser.parse_args()
        fahrenheit = celsius_to_fahrenheit(args.celsius)
        print(f"{fahrenheit:.1f}")
    except SystemExit:
        # Re-raise SystemExit to allow pytest to catch it
        raise
    except Exception as e:
        print(f"Error: Invalid input. Please provide a numeric value.\n{e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()