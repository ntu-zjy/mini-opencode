---
name: code-review
description: Perform thorough code reviews following best practices
---

# Code Review Skill

When reviewing code, follow this checklist:

## Security

- Check for injection vulnerabilities (SQL, XSS, CSRF)
- Verify input validation and sanitization
- Check for hardcoded secrets or credentials

## Performance

- Look for N+1 query patterns
- Check for unnecessary re-renders or computations
- Verify proper use of caching

## Maintainability

- Naming conventions: clear, consistent, descriptive
- Single responsibility: each function does one thing
- DRY: no duplicated logic

## Style

- Consistent formatting
- Meaningful comments (explain "why", not "what")
- Proper error handling

## Output Format

For each issue found, report:

1. File and line number
2. Severity: critical / warning / suggestion
3. Description of the issue
4. Suggested fix
