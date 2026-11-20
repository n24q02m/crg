# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 2.x.x   | :white_check_mark: |
| < 2.0   | :x:                |

## Reporting a Vulnerability

If you discover a security vulnerability, please **DO NOT** create a public issue.

Instead, please email: **quangminh2402.dev@gmail.com**

Include:

1. Detailed description of the vulnerability
2. Steps to reproduce
3. Potential impact
4. Suggested fix (if any)

You will receive acknowledgment within 48 hours.

## Security Best Practices

When using crg:

- **Never commit API keys** to version control
- Use environment variables for embedding configuration
- Keep dependencies updated
- The graph database (`.crg/graph.db`) is local-only; crg writes a `.gitignore` inside `.crg/` so it stays out of version control
- `repo_root` parameter is validated against `.git` or `.crg` presence to prevent path traversal
