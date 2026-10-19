# Security review — After Hours

Reviewed October 17, 2026. Scope: Week2 source, local storage, membership boundaries, private media, external data flows, server configuration and installed dependencies. This was a local code review plus synthetic regression tests and a dependency scan. It was not an independent penetration test, a production deployment assessment, or a guarantee against compromise.

**Verdict: local learning prototype only. Not approved for public hosting or highly sensitive production records.** No evidence of an actual breach was established by this review; historical provider exports, browser activity and downloaded files were not investigated.

## Verified findings and changes

| Finding | Impact before review | Change and verification |
|---|---|---|
| Storage used 0755 directories / 0644 SQLite file | Broader local file readability than needed | Existing/default data directories changed to 0700 and SQLite / photo files to 0600 on POSIX. Files are preserved. Tests cover existing-data permissions and symbolic-link rejection. This does not encrypt contents. |
| Private photos passed to `st.image` | Streamlit can register image bytes in its shared media handler, which is not group authorization | Private scrapbook images now use escaped inline JPEG data URIs after the group access check. The public illustrative hero remains public. Test checks no shared media URL and escaped alt text. Old cached entries require server restart. |
| Key/invitation downloads used `st.download_button` | Bearer credentials could be registered with a shared download handler | These downloads were removed. Keys/codes use session-rendered code blocks with copy controls; save private keys in a password manager. Tests verify no key download is registered. Files users previously downloaded are outside the app's control. |
| Tracing could be enabled through inherited environment settings | LangGraph/profile inputs could be exported without separate tracing consent | Personal workflow entry points force `tracing_context(enabled=False)` before processing. No private node trace decorators remain. A regression test verifies inherited true settings are overridden. This cannot undo previous exports. |
| Read-only Codex mode still enabled shell execution | Prompt instructions alone were insufficient to prevent command use | Shell and unified execution features explicitly disabled, web search disabled, user config/rules ignored, temporary working directory retained. Child environment now uses an allowlist rather than a secret-name denylist. Mocked tests assert flags and filtering. This is not a hardened OS/container isolation boundary. |
| No private-key revocation / invitation expiry | A copied key remained usable indefinitely | Members can replace their own private rejoin key, immediately invalidating the old key. Invitations expire in seven days; only the coordinator can replace them. Existing pre-review invites receive a seven-day expiry when the schema migrates. Tests verify revocation, ownership and expiry. |
| Graph sync lacked separate member consent and could copy scrapbook captions | Optional Neo4j could receive more personal data than necessary | UI restricts sync to the coordinator; the adapter requires each profile's explicit graph consent before writing. Captions are not mirrored by the hardened adapter. Earlier remote copies are not automatically erased by this local review; review/delete them separately where appropriate. |
| Network settings could be overridden for public sharing without a login system | Unauthenticated users could reach a prototype not built for hostile public use | Default bind is localhost, CORS/XSRF enabled, static serving disabled, error details hidden. App refuses non-loopback bind addresses. This does not stop someone deliberately forwarding localhost with a tunnel/reverse proxy; do not do that. |
| Old pip installer had known vulnerability advisories | Unsafe package-installation behavior in the development environment | Updated Week2 pip from 25.0.1 to 26.2.1. Follow-up pip-audit of 69 installed distributions reported no known vulnerabilities. The old report contained duplicate advisory entries; they were all associated with pip. No other installed package was flagged in this scan. |

## Existing protections checked

- Random high-entropy member/invitation keys stored as hashes, not plaintext.
- Group scoping before plan, vote, memory and image retrieval; organizer-only controls and uploader-only memory deletion.
- Parameterized SQLite and Neo4j queries; no model-written SQL/Cypher execution.
- Mandatory group constraints and all-person confirmation are enforced by code, not LLM assertions.
- JPEG/PNG/WebP decoding, size/pixel limits, random image filenames, JPEG re-encoding and EXIF removal.
- External provider failures do not substitute invented facts. Backend calls use fixed API endpoints rather than fetching user-supplied venue URLs.
- SMS requires finalization, real-venue booking attestation, coordinator approval and per-person consent, with persistent duplicate suppression. Tests use mocked requests only.
- `.env`, local databases, uploads, Streamlit secrets and virtual environments are excluded from Git. No credential values were included in review output.

## External data disclosures

| Destination | Data that can leave the machine | Trigger |
|---|---|---|
| OpenAI via Codex CLI | Each consenting person's profile text; derived summaries and option details for the coordinator | Explicit Codex mode action. Use Demo rules for no model call. |
| Open-Meteo / GeoNames | City/ZIP search query; selected city-center coordinates for weather | Explicit search/weather action |
| OSM / Google / Foursquare | Approximate city-center search coordinates and categories | Explicit live-discovery action |
| Configured Neo4j | Consented structured profiles, selected places, plan/vote metadata and memory date/ID | Coordinator action after all profiles opt in |
| Twilio | Opted-in recipient phone number, venue/time/group-size booking text | Explicit organizer Send action after confirmed booking |
| LangSmith | Personal workflow tracing disabled by application code | No supported profile-tracing mode |

Photos are not sent to an LLM. The browser receives a photo only after the server checks membership, but an authorized viewer can always copy it or take a screenshot. Deleting a memory cannot recall copies already saved by viewers or external backups.

## Remaining high-priority work before real deployment

1. **Real identity and access:** OIDC login, optional MFA, verified membership, revocable sessions, recovery and reauthentication for sensitive actions. Current bearer keys prove possession, not a person's identity; there is no administrator identity recovery or central abuse-rate limiter.
2. **Encrypted storage and backups:** current SQLite fields, phone numbers and JPEG files are plaintext on disk. Owner-only permissions do not protect against the same OS user, malware, stolen unlocked devices or copied backups. Use OS disk encryption for local storage, and managed encryption/KMS plus backup controls for hosting.
3. **A proper private media service:** authenticated media endpoints or tightly scoped short-lived object URLs, retention controls and deletion semantics. Inline images are a local-prototype mitigation, not a complete hosted media architecture.
4. **Abuse/operations controls:** per-user rate limits and storage quotas, audited administrative access, secure logs, monitoring, incident response, patching and backup/restore drills. Hosting platform controls have not been reviewed.
5. **Data lifecycle:** export/delete workflows for whole profiles/groups, removal of external mirrors and backups, retention periods and consent history. Existing Neo4j mirrors and previous trace exports require separate review.
6. **Model isolation and minimization:** use an API-only model adapter with no local filesystem tools, or a properly isolated worker/container, before processing very sensitive free text. Do not rely on a model prompt as a security boundary.
7. **Independent review:** run authenticated tests against the actual deployed system and its identity/storage configuration before inviting real remote users.

## What to do now

- Stop Streamlit with Ctrl+C and restart it from `week2` to apply the updated server config and discard old in-memory media/download entries:

  ```bash
  .venv/bin/streamlit run streamlit_app.py --server.port 8502 --server.address 127.0.0.1
  ```

- Do not share a tunnel or publish the current app. Continue testing with fictional data while production controls remain incomplete.
- Replace a private rejoin key if it was copied into a screenshot, shared message or download you no longer control. Replacing it keeps membership but invalidates the old key.
- Keep private keys, API credentials, `.env`, the data directory and backups out of Git. Check local disk/backup encryption through your OS settings; it was not verified by this code review.

## Evidence and limits

54 automated tests pass, including security regression cases for localhost enforcement, local permissions, symlinks, key revocation, invitation expiry, private image rendering, tracing suppression, graph consent and Codex execution restrictions. Previous cross-group/photo/SMS tests remain green. Package-audit summary is in `security/dependency-audit.json`. No real SMS was sent, no real private photo was exfiltrated or used as a test fixture, and no public site was deployed during the review.

References: [Streamlit configuration](https://docs.streamlit.io/develop/api-reference/configuration/config.toml), [Streamlit OIDC](https://docs.streamlit.io/develop/concepts/connections/authentication), [Codex feature configuration](https://learn.chatgpt.com/docs/config-file/config-basic), [LangSmith tracing context](https://kb.langchain.com/articles/2491399069-how-do-i-disable-or-toggle-langsmith-tracing-during-execution).

Simple ZIP groups use the existing hashed membership and expiring invitation
system. Invite URLs carry only the group invitation; joining issues a separate
private member key, and a display name cannot restore another member's session.
Invite query parameters are removed from the app URL after consumption.
Response writes derive member identity from the private key. Finalization checks
coordinator ownership, every member's response, and compatibility for definite
attendees inside a write transaction. Finalized simple groups reject new joins.
Text invitations prepare a local messaging-app draft, with no provider call or
SQLite phone storage. Remote phone sharing is not deployed; the localhost gate
remains. Existing production authentication/rate-limit/encryption limitations
still apply. The basic ZIP flow does not claim verified hours or distance limits.

The second-stage venue feature uses membership-scoped SQLite rounds and ballots.
Only the coordinator searches/opens/finalizes; each person writes their own ballot.
Draft metadata freezes at voting, and finalized venues cannot be replaced. All
available/tentative members must vote; every definite attendee must positively
accept the chosen venue. Known over-budget venues cannot be finalized. Model
requests require relevant members' opt-in, use aliased responses and public venue
data, disable tracing, reject unsupported candidate IDs and stale results, and
never book a reservation or send an SMS. Consent can change independently of
frozen preferences, and such changes invalidate displayed recommendations.
Ratings/costs are unknown unless explicitly supplied; organizer-entered values
require a source URL. Live-provider validation remains pending host credentials.
Existing local-only authentication/hosting limitations remain unchanged.

Group departure now marks memberships inactive and revokes their bearer key.
Active roster/response queries exclude departed members; personal profile and
simple response fields and SMS contact preferences are cleared. Historical member
IDs/names remain for authorship; this is not complete historical data erasure.
The departing member may explicitly delete their own memories and associated
private image files. Otherwise those memories remain shared with active members.
Only the coordinator can transfer that role, and an active successor is required
when others remain. Last-member departure invalidates invitations. Gallery reads
recheck membership on each refresh; photo inserts recheck active membership under
a write transaction. Already-viewed/downloaded photos cannot be recalled.

## Creator authentication update — October 18

The default event-creation flow now requires Google OIDC through Streamlit's
native login. No app password is collected. A verified Google issuer, subject
and verified-email claim are required. Account membership links use the stable
provider subject hash; matching a typed name/email cannot restore an identity.
Creator group recovery is scoped to active linked memberships and rotates the
old member key. The old detailed creation route directs to this guarded flow.

This supersedes earlier notes that creator sign-in was entirely unimplemented.
Google client credentials and a cookie secret still require host setup; the live
browser callback is unverified. Guest joining still uses bearer membership
sessions, and existing unlinked groups are not automatically claimed by an
account. This change does not authorize public hosting or establish complete
production access control. The localhost guard remains enabled.
