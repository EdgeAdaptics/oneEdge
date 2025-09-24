# Attestation Service (Stub)

Future home for attestation verification APIs. For now it simply documents the intended responsibilities:

- Validate evidence from devices (firmware hash, nonce, TPM quotes)
- Persist attestation results into Postgres via the console API
- Emit events for the console UI / audit trail

Implementation deferred to a later milestone.
