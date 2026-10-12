# AI Rules interpreted by the Claude Code session (SESSION mode)

**Why.** Bank AI Rules need an AI only once per rule text: to translate the rule into a structure the code
executes (`ai_rules.validate_interpretation`, BANK_AI_RULES_008). In the local environment that translation is
done by the Claude Code session in VS Code — no AWS, no API key. The interpretation is saved in the database
(`bank_ai_rule_interpretations`, provider `CLAUDE_CODE_SESSION`), so it travels with the database to the other PC.

## What the Preview button does (SESSION mode)

| The rule text (with the current general AI instructions) | Preview |
|---|---|
| already has a saved interpretation that represents every instruction | **runs at once, by code, 0 AI calls**; shows the instructions represented and the provider/model that interpreted it |
| has a saved interpretation that does NOT represent every instruction | **blocked**, with the reason; no simplified version runs |
| has no saved interpretation | **waits for the session**: "In attesa della sessione Claude Code (Preview #N)…". No provider is called — never a silent fallback to AWS |

Any change of the rule text or of the general AI instructions is a new text: it needs the session again.
"Salva" of an operative rule needs a saved interpretation (Preview first).

## Automatic: one click on Preview (BANK_AI_RULES_012)

With `"claude_code_cli": "auto"` in `environment.json` (the default; `"off"` restores the waiting behaviour
above), **Avvia Bank** passes `RFONE_BANK_CLAUDE_CODE_CLI=auto` to the server. A rule text with no saved
interpretation is then interpreted **in the same Preview request** by the Claude Code CLI installed on this PC
(the `claude.exe` of the newest Claude Code VS Code extension, else `claude` on PATH) — the same program and the
same login as the VS Code session, **no AWS, no API key**:

* print mode, JSON output, **no tools**, no session kept, a neutral empty folder, model `claude-opus-5-5`
  (`RFONE_BANK_CLAUDE_CODE_MODEL`); the prompt is exactly the one `run.ps1 session prompt N` writes;
* the answer is validated by Bank's validator — an incomplete or partial interpretation is **blocked**, never
  executed in part — and saved with provider `CLAUDE_CODE_CLI`; the preview then runs by code;
* the page shows a spinner meanwhile; text and options stay in the window; nothing is ever applied;
* a CLI failure (not signed in, timeout, an answer that is not JSON) makes the preview FAILED with that reason,
  and nothing is saved. Signing in again in Claude Code (VS Code) fixes a login problem.

The manual procedure below stays valid, e.g. with `"off"` or when the CLI is not installed on a PC.

## What the Product Owner does (manual procedure)

1. Press **Preview**. If it says *In attesa della sessione Claude Code*, write in the Claude Code session in
   VS Code: **«Interpreta le AI Rules in attesa»**.
2. When the session confirms, press **Preview** again.

## What the session does (instructions for Claude Code)

From `03 Software/Infrastructure/Bank Local Environment` (add `--profile test` for the test copy):

```powershell
run.ps1 session pending                 # the rules waiting: Preview #N and text
run.ps1 session prompt N                # writes the EXACT prompt Bank would send:
                                        #   %LOCALAPPDATA%\RF-One\Bank\session-interpretations\prompt_N.txt
```

Read the prompt and answer it **exactly as the prompt asks** — you are the AI the prompt addresses:

* JSON only, the structure the prompt defines (`kind`, `conditions`, `who`, `why`, `status`,
  `only_if_who_differs`, `replace_existing`, `branches`, `coverage`, `unsupported`);
* every text copied exactly from the rule;
* `coverage`: every instruction of the rule, one entry each, with the element that carries it out — and say
  where RF-One's protections apply (manual / Standard decisions stay PROTECTED);
* an instruction no element can carry out goes in `unsupported` and the answer is `OTHER` — never a simplified
  structure, never a dropped condition.

Save it as `answer_N.json` in the same folder, then:

```powershell
run.ps1 session answer N "%LOCALAPPDATA%\RF-One\Bank\session-interpretations\answer_N.json" --model <your model id>
```

It is validated by Bank's own validator and saved; the command says EXECUTABLE or BLOCKED (with the reason).
Report to the Product Owner which instructions were represented and how, and that they can press Preview again.
Nothing else is written (no movement, rule or preview). Use the model id you are actually running as.

## Switching to a provider

Only explicitly: `Avvia Bank` with `--ai PROVIDER` (uses `RFONE_AI_PROVIDER`, e.g. AWS Bedrock, which needs
valid credentials). The page header always shows the AI mode in force.
