# Organization > Interviews TEST — deployed 2026-11-01

Supersedes the initial release's global Admin + EMPLOYEES requirement for interview request/results pages. Approved user decision: temporarily place Interviews under Organization with its authorization checkbox.

AWS App Runner operation `d871cb97f22c4ba0ba785092327c4d04` SUCCEEDED; service RUNNING. Application commit `764241237e0619de5bf669a9b1a9d9c6cb941ea6`, branch `codex/interviews-aws-test-20261101`. Image `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:interviews-test-20261101t202720z`; digest `sha256:999c3b22e7103b32aa936e74de63cad6cc4e732514bfa4f24b43fcd04f81e593`. CodeBuild `rfone-web-build:4aa58c38-6b41-4282-9185-c2c05fb46cbc` succeeded. Source: `s3://rfone-tips-deploy-418674484214/releases/interviews-test-20261101t202720z/source.zip`.

## Configure access

Open https://rfone.romesflavours.com/admin/accounts as an RF-One administrator. Choose Shelbi > Access > Organization > Only selected items, tick Interviews · TEST, preserve any other intended items, and save. The existing Whole Domain mode also includes Interviews. No individual account grants were changed during deployment.

The `interviews` item drives authorization choices, Organization navigation, direct request/results routes and service checks. Global administrator status and full directory access are no longer required. Results remain limited to their requester. Full person record links appear only with separate EMPLOYEES access. The participant's assigned interview remains available through MyRF without this management permission. TEST remains visible.

## Verification

13 interview tests passed, including non-admin selected-item access, request/results, revocation and unrelated-page denial. Existing account/item authorization suite: 92 passed, 0 failed. Image layout startup and Tips registration passed. An additional isolated HTTP check verified the actual access form renders and saves the Interviews checkbox and enables an ordinary user while Accounts and full directory remain forbidden. Public HTTPS probes passed for login, protected interview redirects, existing directory/Selection/Training entry points and feature assets. No real interview, real account grant or microphone/AI acceptance session was created for verification.

No schema changes or migration were needed. Only the web image changed; existing service configuration was retained. Roll back the image to `418674484214.dkr.ecr.us-east-1.amazonaws.com/rfone-web:interviews-test-20261101t195949z` if needed; that restores the prior authorization behavior. No Git push was performed.
