<!-- Behavioral pytest testing guidance for generated projects. -->
---
name: testing_patterns
description: Patterns for writing pytest tests.
triggers: [test, pytest, test_, assertion]
tags: [testing]
---
- One behavior per test function.
- Test edge cases: empty input, invalid input, very long input.
- Use descriptive test names: test_<feature>_<condition>_<expected>.
- Use pytest.mark.parametrize for multiple similar cases.
- Never assert on implementation details; assert on behavior.
