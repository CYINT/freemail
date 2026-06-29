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
- Add license scanning to CI before the first release tag.
- Document any ambiguous component before bundling it.
