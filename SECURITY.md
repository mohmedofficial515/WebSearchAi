# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| 0.1.x   | ✅ |
| < 0.1   | ❌ |

## Reporting a vulnerability

**Do not open a public issue** for security bugs.

Email the maintainer (or use GitHub's [private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)).

We aim to:
- Acknowledge receipt within 72 hours
- Provide a fix or mitigation within 14 days for high-severity issues
- Credit you in `CHANGELOG.md` and the release notes (unless you prefer anonymity)

## In scope

- Prompt-injection attacks that exfiltrate data or escape the sandbox
- Cross-task data leakage (one user reading another user's outputs)
- RCE through malicious page content
- Credential leakage in logs or screenshots
- Path-traversal in artifact endpoints

## Out of scope

- Vulnerabilities in third-party sites the agent visits (not our code)
- Self-XSS that requires the operator to paste hostile input themselves
- Rate limiting / DoS — Phase 8 will harden this
