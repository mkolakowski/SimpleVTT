# Credits & Attribution

SimpleVTT is built on top of several openly-licensed works. This file is the
canonical attribution record for everything that ships in the repo or is
fetched at runtime.

The project source code is © Matthew Kolakowski and licensed MIT; see
[LICENSE](LICENSE). The third-party material below carries its own
license, summarized here.

---

## Game-rules content (D&D 5e SRD)

The ~984 JSON files under `app/data/local/dnd5e/` are mechanical-summary
adaptations of the D&D 5e System Reference Document (SRD 5.1) sourced from
the [Open5e](https://open5e.com/) public API.

- **Original work:** Wizards of the Coast — *Systems Reference Document 5.1*
  - Licensed under [Creative Commons Attribution 4.0 International (CC BY 4.0)](https://creativecommons.org/licenses/by/4.0/)
  - Also available under the [Open Game License v1.0a (OGL 1.0a)](http://opengamingfoundation.org/ogl.html)
- **Intermediate source:** [Open5e](https://open5e.com/) — community-maintained REST API mirror
  - Licensed [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
  - API endpoint: `https://api.open5e.com/v1/`
- **Generation script:** [`scripts/build_srd_content.py`](scripts/build_srd_content.py)
  - Filters to `wotc-srd` document slug only (no Tasha's / Xanathar's / third-party expansions)
  - Each generated file carries an `_attribution` field with the same credit chain

If you redistribute or modify this project you must preserve the per-file
`_attribution` metadata and (per CC BY 4.0) provide credit to both Wizards of
the Coast and Open5e in any user-visible distribution.

### A few records sourced from SRD 5.2 (2024 rules)

Most shipped content adapts **SRD 5.1**. A small number of records adapt the
later **D&D 2024 System Reference Document (SRD 5.2)**, also released by
Wizards of the Coast under [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) —
specifically the **Goliath** and **Aasimar** species
(`app/data/local/dnd5e/races/{goliath,aasimar}.json`), which are part of the
SRD 5.2 core species list but were never in SRD 5.1. These carry the 2024
mechanics (so they differ from their pre-2024 sourcebook versions) and an
`_attribution` field citing SRD 5.2. Non-SRD races (e.g. Firbolg, Genasi, the
pre-2024 "Variant Human") remain outside the shipped tier — they belong to the
campaign/operator homebrew tier.

---

## Frontend dependencies (loaded from CDN at runtime)

- **[htmx](https://htmx.org/) v1.9.12** — [BSD 2-Clause](https://github.com/bigskysoftware/htmx/blob/master/LICENSE) — loaded from `unpkg.com`
- **[Google Fonts](https://fonts.google.com/)** — [SIL Open Font License 1.1](https://scripts.sil.org/OFL):
  - Cormorant Garamond (headings)
  - Lora (body)
  - IM Fell English (fantasy theme accent)

---

## Python dependencies (declared in `requirements.txt`)

| Package | License |
|---------|---------|
| [fastapi](https://fastapi.tiangolo.com/) | MIT |
| [uvicorn](https://www.uvicorn.org/) | BSD-3-Clause |
| [SQLAlchemy](https://www.sqlalchemy.org/) | MIT |
| [psycopg2-binary](https://www.psycopg.org/) | LGPL-3.0 (the driver itself; `psycopg2` C-extension code may impose extra obligations on linkers — pip-installing the prebuilt wheel from PyPI does not) |
| [alembic](https://alembic.sqlalchemy.org/) | MIT |
| [Jinja2](https://jinja.palletsprojects.com/) | BSD-3-Clause |
| [python-multipart](https://github.com/Kludex/python-multipart) | Apache-2.0 |
| [itsdangerous](https://itsdangerous.palletsprojects.com/) | BSD-3-Clause |
| [passlib](https://passlib.readthedocs.io/) | BSD-2-Clause |
| [bcrypt](https://github.com/pyca/bcrypt/) | Apache-2.0 |
| [Authlib](https://authlib.org/) | BSD-3-Clause |
| [httpx](https://www.python-httpx.org/) | BSD-3-Clause |
| [pydantic](https://docs.pydantic.dev/) | MIT |
| [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) | MIT |
| [websockets](https://websockets.readthedocs.io/) | BSD-3-Clause |
| [python-jose](https://github.com/mpdavis/python-jose) | MIT |
| [email-validator](https://github.com/JoshData/python-email-validator) | CC0-1.0 |
| [mutagen](https://mutagen.readthedocs.io/) | GPL-2.0-or-later (used at runtime only to read audio file metadata; not linked into the binary) |
| [Pillow](https://python-pillow.org/) | HPND |

Each project's full license text is available at the linked homepage or by
running `pip show <package>` against an installed environment.

---

## Reporting an attribution issue

If you believe content shipped here is missing attribution or is licensed
under terms incompatible with the chain above, please open an issue at
[github.com/mkolakowski/SimpleVTT](https://github.com/mkolakowski/SimpleVTT)
(or contact the project owner directly) with the specific file path and
the conflicting source.
