# Conoscenza — persistent RF-One project knowledge

**Tasks:** `07 Tasks/CONOSCENZA_01_Incarico_Claude.md` (first local flow) and the Product Owner's AWS
release order of 2026-11-24 (`Decisioni RF1.md`, "Conoscenza su AWS: autorizzazione al deploy e registro
per più persone").
**Status:** released on AWS (App Runner service `rfone-conoscenza`, schema `conoscenza` in the RF-One RDS
instance). Access is reserved to the owner (Pino) in this release.

## Purpose

A new chat — of ChatGPT, Claude or Codex — starts without memory of earlier chats. Conoscenza keeps,
inside RF-One, what Pino decides, the corrections he explains (with their reason, validity limits and
exceptions) and the outcomes of the work (with evidence), and lets the next session of ANY of the three
tools retrieve the pertinent part **before** proposing or resuming work, even when Pino uses different words.

Relation to `01 Domains/Shared Domains/Know-How/`: Know-How is the business Shared Domain for the
organizational know-how of the businesses using RF-One; Conoscenza is a system capability for the
project's own decisions and work. Whether Conoscenza becomes an application of Know-How is an **open
question** for the Product Owner; nothing here changes Know-How.

## People, tools and authority

Every entry keeps three distinct attributions:

| Attribution | Column | Meaning |
|---|---|---|
| Person who provided it | `contributed_by_person_id` | Whose contribution it is (NULL = unknown; undocumented history stays unknown). |
| Tool that recorded it | `recorded_by` | `CLAUDE`, `CODEX`, `CHATGPT` or `IMPORTER`, always taken from the credential. |
| Who decided or approved | `decided_by_person_id`, `decided_by` | For decisions only. |

`authority`: `PO_EXPLICIT` (decision taken or approved by the owner, Pino), `PROPOSAL` (another person's
proposal, not approved), `AI_HYPOTHESIS` (the AI's reading, never a decision), `EVIDENCE` (work outcome).
Only the owner creates `PO_EXPLICIT` entries. When the owner approves a proposal (`conoscenza_approva`),
a new `PO_EXPLICIT` version is created, still attributed to the proposer; the proposal stays as the
previous version and `conoscenza_approvals` records who approved, through which tool and when.

Prepared for more people (Shelbi and other collaborators, later): `conoscenza_people` and
`conoscenza_access_rules` (`READ`, `CONTRIBUTE`, `APPROVE` per domain prefix, `*` = all). A non-owner
reads and contributes only where a rule allows it; no rule = no access; the access history is reserved to
the owner. **In this release the only person is Pino; no other person, rule or credential exists.** The
limits and filters for others are to be defined by the Product Owner.

## Model (code: `03 Software/RF-One Data Store/rfone_data_store/conoscenza/`)

| Table | Content |
|---|---|
| `conoscenza_items` | Decision, motivated correction or work update, one row per version (series, version, status CURRENT/SUPERSEDED). Domain, title, statement, rationale (+ KNOWN/UNKNOWN), validity, exceptions, keywords, attributions, source type/reference/excerpt, work reference and stage. |
| `conoscenza_evidence` | Evidence of a work update: COMMIT, TEST, RELEASE, DOCUMENT, FILE, OTHER. |
| `conoscenza_links` | AMENDS (partial change) or RELATES between series. |
| `conoscenza_approvals` | Owner approvals of proposals. |
| `conoscenza_people`, `conoscenza_access_rules` | People and their permissions. |
| `conoscenza_clients` | Credentials: one person + one tool; only the SHA-256 of a token is stored. |
| `conoscenza_oauth_clients`, `conoscenza_oauth_grants` | ChatGPT OAuth registration, codes, access and refresh tokens (hashed). |
| `conoscenza_access_log` | Every brief, search, read, write and OAuth authorization, with person, tool, session, query, returned entries and outcome. |

Rules (`service.py`): one CURRENT version per series; an AI hypothesis or proposal never replaces an owner
decision; work stages need evidence (IMPLEMENTED: any; VERIFIED: TEST or RELEASE; RELEASED: RELEASE);
the same request key never creates a second row; every write returns the entry read back from the register.
Retrieval (`search.py`) is offline and concept-based (Italian/English synonym groups, stems, weighted
fields, BM25-like scoring) plus the keywords stored by the recording AI.

## Architecture on AWS

```
Claude Code ─ stdio ─┐                                     ┌─ RDS PostgreSQL (rfone-dev), database rfone,
Codex ─────── stdio ─┤ conoscenza.py mcp (local proxy,     │  schema conoscenza, role conoscenza_app
                     │ queue for offline writes) ─ HTTPS ─┐│  (uses only its schema; private)
ChatGPT ── OAuth 2.1 + MCP Streamable HTTP ── HTTPS ──────┴┴─ App Runner rfone-conoscenza (VPC egress
                                                              rfone-nat-connector), /mcp + /oauth/*
```

- **Service:** `rfone_data_store/conoscenza/http_app.py` (Flask + gunicorn), image built from a
  Conoscenza-only snapshot (`03 Software/Infrastructure/deploy/rfone-conoscenza/`). `/health` does not touch
  the database; the schema is never migrated at startup.
- **Authentication:** `Authorization: Bearer` with a tool credential (Claude Code, Codex) or an OAuth access
  token (ChatGPT; dynamic client registration, authorization code + PKCE S256, 8-hour access tokens, 90-day
  rotating refresh tokens). The OAuth authorization page asks for the ChatGPT access key of the person, so
  the grant is bound to that person and to the tool CHATGPT.
- **Database:** secret `rfone-conoscenza/database-url` (role `conoscenza_app`, search_path `conoscenza`).
  The App Runner instance role reads only `rfone-conoscenza/*` secrets.
- **Setup/migration:** `conoscenza_aws_setup.py`, run once as an ECS Fargate task (`rfone-conoscenza-setup`)
  inside the VPC: creates role and schema, creates tables, imports the export of the first-release register
  with its ids, prints a per-table manifest (row count + SHA-256) compared with the local export.
- **Offline writes:** the local proxy assigns the request key before the first attempt; if AWS cannot be
  reached the write is queued in `output/conoscenza/pending/` (Git-ignored) and is sent automatically before
  the next successful call (or by `conoscenza.py riprova`). The service treats a repeated key as the same
  write, so each queued write reaches the register exactly once.

## Client entry points

| Client | Entry point | Configuration |
|---|---|---|
| Claude Code | `CLAUDE.md` section "Conoscenza" + `.mcp.json` (server `conoscenza`, local proxy) | `Secrets/conoscenza/remote.json` (`{"url": ...}`) points the proxy at AWS; token `Secrets/conoscenza/claude.token`. Pino approves the project server once. |
| Codex | `AGENTS.md` section "Conoscenza" + `.codex/config.toml` | Same proxy with token `codex.token`. Non-interactive runs need `default_tools_approval_mode = "approve"` under `[mcp_servers.conoscenza]` (to be set by Pino). |
| ChatGPT | Custom MCP connector, URL `https://<service>/mcp`, OAuth | On authorization, paste the key in `Secrets/conoscenza/chatgpt.token`. Write tools may depend on the ChatGPT plan. |

The local first-release register `03 Software/RF-One Data Store/data/conoscenza.db` is kept as a backup
copy only (plus `conoscenza.backup-20261124-pre-aws.db`); it is not a second working register.

## Command line

`python "03 Software/RF-One Data Store/conoscenza.py" --client <claude|codex|importer> <command>` —
`contesto`, `cerca`, `leggi`, `registra`, `cambia`, `approva`, `collega`, `accessi`, `riprova`, `mcp`
(remote when configured); local administration: `init`, `importa`, `importa-estratto`, `migra-esporta`,
`manifest`.

## Tests

`python "03 Software/RF-One Data Store/test_conoscenza.py"` — disposable registers under `RF One/tmp/`;
55 checks, including attribution, proposals/approval and access rules, OAuth (registration, PKCE, single-use
codes, refresh rotation), MCP over HTTP, the remote proxy with offline queue and exactly-once replay, and a
migration dry run on the real first-release register.
