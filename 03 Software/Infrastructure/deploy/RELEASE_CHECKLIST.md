# RF-One release checklist

This checklist collects the existing CLAUDE.md, How Works, language and documented
AWS deployment requirements. It introduces no new approval requirement.

1. Confirm the user-authorized module and deployment target; keep unrelated local
   changes out of the release. Preserve existing authentication and account grants.
2. Prepare an English interface, contextual page/modal help and authorized visible
   data. Preserve identifiers, numerical facts, proper names and source evidence.
3. Run relevant service/HTTP/browser checks, image-layout startup and
   `03 Software/Shared UI/check_how_works.py` against the actual release artifact.
4. Freeze the tested source in version control. Build from that immutable snapshot;
   record source hashes and image digest. Exclude credentials, local databases,
   automatic local-login launchers and unrelated applications.
5. Record the prior service/routing/image state and recovery references before
   modifying AWS. Apply reviewed additive schema changes explicitly, never at
   application startup. Publish only the domain content explicitly authorized;
   do not synchronize local working databases into AWS.
6. Build and deploy the intended image using the configured AWS workflow. Protect
   uploaded media with persistent private storage. Follow the operation to its
   terminal result; verify readiness, authorization boundaries and official routing.
7. Record outcome, URLs, source/image versions, data checks, remaining scope and
   rollback references. Do not claim deployment success from a submitted build alone.
