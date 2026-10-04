# Safety model

Operational automation runs against systems and data that may be difficult to recover. This repository follows five rules.

## Read-only by default

Fleet, certificate, and backup commands only inspect state. Cleanup defaults to preview and lists exact candidates. Mutation requires both `--apply` and the literal confirmation `DELETE_EXPIRED_FILES`.

## Explicit scope

Every host, endpoint, backup directory, and cleanup root is declared in configuration. Cleanup ignores directories and symbolic links, resolves its configured root, and applies age plus protection rules only inside that root.

## Partial failure is visible

An unreachable SSH host is `FAIL`; checks skipped afterward are `UNKNOWN`, never `PASS`. Commands return non-zero when any check fails so a scheduler or monitoring platform can alert.

## Evidence survives execution

The tool writes timestamped JSON or Markdown reports containing target, check, status, summary, and captured evidence. Generated reports are ignored by Git because they can contain environment details.

## Scheduling is separate from logic

The systemd example uses a dedicated account, hardened service options, a persistent timer, and a randomized delay. Production credentials and inventory remain outside the repository.

## Known boundaries

- Backup freshness does not prove recoverability. Add isolated restore testing for production assurance.
- Certificate checks use the local trust store and do not implement private-CA configuration or revocation checks.
- Fleet commands are declared by a trusted operator; inventory files are executable configuration and must be access-controlled.
- This toolkit reports operational state. Connect alerts or ticketing through a separate, authenticated integration.

