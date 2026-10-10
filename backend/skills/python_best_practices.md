<!-- Clean Python implementation guidance for generated projects. -->
---
name: python_best_practices
description: Rules for clean, safe Python code.
triggers: [python, .py, pytest]
tags: [language, style]
---
- Always use type hints on function signatures.
- Always write docstrings for classes and public methods.
- Never use bare `except:`. Catch specific exceptions.
- Prefer pathlib over os.path.
- Use f-strings, not % or .format().
