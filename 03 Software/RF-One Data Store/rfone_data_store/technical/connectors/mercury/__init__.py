"""The Mercury Technical Connector (TASK_TIPS_CORE2_PILOT).

Owns only Mercury Banking API integration concerns (authentication, HTTP
client, request/response shape, provider-specific error interpretation) —
never Tip calculation logic, Payment Instruction identity, or any other
Domain-specific decision (`01 Domains/Business Domain/Restaurant/Tips/Tips
Payment Execution.md`). Nothing here is imported by `rfone_data_store.models`
— the dependency runs one way, exactly like the Clover connector.

SANDBOX ONLY in this task: `MercuryClient` defaults to
`https://api-sandbox.mercury.com/api/v1/` and reads its token from the
`MERCURY_SANDBOX_API_TOKEN` environment variable. No production endpoint or
token is referenced anywhere in this package.
"""
