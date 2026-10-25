# Event contracts (PE-6)
One JSON Schema per `<type>.v<schema_version>.json`. Rules:
- Within a schema version, changes are **additive** (new optional fields). Removing/renaming a field or changing a
  type means a new `schema_version`, and producers keep emitting the old version until every consumer reads both.
- `fixtures/*.r<release>.json` are real events captured from each release. The replay test feeds every fixture to every
  current consumer, so a deploy can never break events already in queues, DLQs or the outbox from the previous release.
