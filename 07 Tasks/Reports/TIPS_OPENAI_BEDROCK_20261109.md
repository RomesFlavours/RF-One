# REPORT — Tips OpenAI via private Bedrock

## 1. Outcome

AWS rfone-tips is RUNNING. Deployment operation `b100b4a25a2945bca5ae14183ccd50c3` SUCCEEDED.
Tips now uses OpenAI GPT-OSS 120B (`openai.gpt-oss-120b-1:0`) through the existing
private Bedrock Runtime endpoint. No NAT, OpenAI/Anthropic API key, database
migration, import, synchronization or business-data modification was performed.

The local copy has the same Tips provider code and dedicated configuration in
its ignored `.env`, using the existing `rfone-dev-login` AWS profile. Generic AI
settings for other modules were preserved. No active local Tips server required
a restart. Source checkout changes belonging to other tasks were not committed.

## 2. Observed problem and implemented correction

Tips had no Anthropic API key or AI provider runtime configuration; its default
selected direct Anthropic, failing before any model request. The App Runner VPC
has no NAT and cannot call public AI APIs. The Product Owner rejected NAT and
requested OpenAI through Bedrock. A live model probe and rule interpretation
confirmed account access to the selected OpenAI model.

Tips now has its own provider function/settings while preserving shared clients'
existing defaults. Converse uses AWS credentials (App Runner instance role on AWS,
the existing named profile locally), ignores reasoning blocks when parsing final
JSON, and rejects truncated/invalid/non-object responses without provider fallback.
The existing validation and human-confirmation flow remains unchanged.

The instance role received only `bedrock:InvokeModel` for the exact selected model
through inline policy `rfone-tips-openai-bedrock`. Runtime secret references and
network configuration were compared before/after and remain identical. No NAT
resource exists after the release.

## 3. Verification

- Committed release runtime: 45/45 synthetic rule-authoring checks passed.
- Tips OpenAI/Bedrock transport and routing: 6/6 tests passed.
- Shared provider backward compatibility: 14/14 checks passed.
- Live local Bedrock rule interpretation: PROPOSED, 10.0000, no database access.
- Live authenticated AWS GET and interpretation POST: HTTP 200; valid proposal,
  10.0000 of TIP_PLUS_GRATUITY. Confirmation was never submitted.
- How Works: technical-only declarations; unchanged templates checked against the
  existing normative registry/checker, zero errors. No page or help change.
- Database diagnostics used read-only transactions. A disposable existing ECS
  runner task retrieved the existing admin's session version for verification;
  its entrypoint ran 16 synthetic connector tests and a read-only schema check.
  The task is stopped. No source synchronization or production writes occurred.
- Synthetic databases were in memory or disposed/deleted after testing.

## 4. Packaging dependency

The initial build correctly refused the old source archive because it lacked
migration e1b220261102, already applied on AWS. The retry included that exact file
and revision registry from published dependency commit
`421f793794619f582dbe784b97cde778f77aa173` (`origin/fix/shared-migrations`). The
migration-chain check passed. No migration was executed.

The release overlaid the committed runtime files onto the exact source archive of
the previous live image, preserving all other live code. Only the image tag in the
existing buildspec and the committed migration dependency metadata were added.

## 5. Traceability and rollback

- Runtime code commit: `4400e5c0025c87d94dad56be4a6e00210563a8ba`.
- Git branch: `fix/tips-openai-bedrock`.
- Build: `rfone-tips-build:cf78a0a6-5215-48c1-a6af-0d99266dfc4f` (SUCCEEDED).
- Image: `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-tips:tips-openai-bedrock-20261109t140457z`.
- Digest: `sha256:fd84ecf14edf10f98811f4c5a977d0c2990f8ef1f85ee80a7616bc5155360c09`.
- Source: `s3://rfone-tips-deploy-418674484214/releases/tips-openai-bedrock-20261109t140457z/source-compatible.zip`.
- Source SHA-256: `614dd45aa9010d9b05a25ac7bd72364631f3db61b7c3cb83f5434415de84076e`.
- Previous image: `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-tips:identity-record-holds-20261102t123252z` (retained).
- Prior service configuration and machine-readable verification:
  `tmp/tips_openai_20261109/previous_service.json` and `release.json` in the local
  RF One checkout. These contain resource references, never secret values.

Rollback: restore the previous image and previous runtime environment from the
saved service configuration, and remove only `rfone-tips-openai-bedrock` if unused.
The network configuration and database need no rollback because neither changed.
