# Chatbot

## Legacy memory ownership

The initial schema stored `agent_memories.user_id` as free-form text (for example, `default_user`) and did not retain a trustworthy link to an authenticated account. The authentication migration therefore does not guess an owner: those rows are preserved for retention/audit, but the authenticated memory API only matches the UUID from the active user's JWT. Legacy rows remain intentionally inaccessible to user-scoped conversations until an explicit ownership mapping is supplied.

To verify this policy, inspect the legacy rows with `SELECT user_id, COUNT(*) FROM agent_memories GROUP BY user_id`; authenticated searches must use `WHERE user_id = '<active-user-uuid>'` and must not fall back to `default_user` or another textual identifier.
