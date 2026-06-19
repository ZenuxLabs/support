<!--
Thanks for contributing to Zenux Support!

Please read CONTRIBUTING.md first. For large or architectural changes, open an
issue to discuss before sending a PR. Do NOT include real customer data,
credentials, or PII in code, tests, or fixtures — use synthetic data only.
-->

## Summary

<!-- What does this PR do and why? -->

## Related issue

<!-- e.g. Closes #123. Open an issue first for large changes. -->

## Type of change

- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that changes existing behavior/contracts)
- [ ] Documentation / runbook update
- [ ] Chore / tooling / CI

## Testing done

<!-- Describe how you verified the change. Per the README: -->

```bash
python3 -m py_compile supportctl/*.py tests/*.py
python3 -m unittest discover -s tests -v
```

<!-- Paste relevant results, redacting any real identifiers. -->

## Checklist

- [ ] PR is focused on a single concern
- [ ] I ran the build/tests described in the README and they pass
- [ ] I added or updated tests where behavior changed
- [ ] Docs / runbooks updated (or not applicable)
- [ ] No secrets, credentials, real customer data, or PII are included
- [ ] I signed off my commits (DCO) — `git commit -s` (see CONTRIBUTING.md)
