# Tavern Tales Preference Data Notes

**Created:** 2026-04-28

These notes document local-first data choices that should remain stable when Tavern Tales later adds account or network sharing.

## Identifiers

- Profiles use stable `profileId` values and belong to a `userId`.
- Saved fantasies use stable `id` values and store `ownerProfileId`, `ownerUserId`, and `createdFromProfileVersion`.
- Profile import intentionally creates a new `profileId` to avoid local conflicts.
- Fantasy import remains separate from profile import and copies the draft into the currently selected profile.

## Export Boundaries

- Profile exports include owner metadata and explicitly state that fantasies are not included.
- Fantasy exports include owner metadata and are controlled by export mode.
- Profile and fantasy exports remain separate by product decision.
- Private comments are omitted unless the user explicitly chooses a private-inclusive path.
- Password-protected fantasy content requires a password for content-bearing export modes.

## Schema Migration Strategy

- Preference profiles carry `schemaVersion`.
- Saved fantasies carry `schemaVersion`.
- Campaigns carry the app-level campaign schema version and a typed `preference_context`.
- New fields should be added with defaults so old local data can be read and normalized through Pydantic models.
- Breaking schema changes should add explicit migration functions in `preference_store.py` before validation, rather than ad hoc UI conversion.

## Encryption Key Strategy

- Current mode is local-key automatic.
- The active key can be exported through the Preference Profiles UI as a backup JSON file.
- Losing the key can make encrypted preference/fantasy files unrecoverable.
- Anyone with both the key backup and encrypted local data can decrypt those files.
- Future sync should not upload the raw local key by default. Account sync should use a separate user-controlled wrapping key or explicit user migration flow.

## Future Sharing

- Network/account sharing should treat local profile ids as source ids, not global identity.
- Shared payloads should include owner/source metadata, schema version, and export mode.
- Multi-profile compatibility should extend the current two-profile comparison shape rather than replacing it.
