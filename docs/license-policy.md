# License Policy

FreeMail is licensed as `AGPL-3.0-or-later`.

## Allowed By Default

- AGPL-compatible copyleft dependencies.
- LGPL libraries.
- Apache-2.0 libraries and tools.
- MIT, BSD, ISC, PostgreSQL License, and similarly permissive software.

## Avoid

- SSPL.
- Business Source License.
- Elastic License.
- Commons Clause.
- Proprietary SDKs required at runtime.
- Field-of-use restricted licenses.
- Proprietary spam, reputation, or deliverability feeds.

## Required Practice

- Update `THIRD_PARTY_NOTICES.md` when adding runtime dependencies.
- Run `python scripts/qa_license_policy.py` before publishing changes. CI runs this gate for direct Python runtime dependencies and direct mobile runtime dependencies.
- Document any ambiguous component before bundling it.
