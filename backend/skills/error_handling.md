<!-- Safe error handling guidance for generated projects. -->
---
name: error_handling
description: Rules for safe error handling.
triggers: [error, exception, try, except, log]
tags: [safety]
---
- Log errors to a file, not print().
- Never expose stack traces to the end user.
- Graceful degradation: if a non-critical step fails, keep going.
- Return clear, actionable error messages.
