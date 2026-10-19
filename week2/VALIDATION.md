# Validation record

Executed October 17, 2026 with Python 3.12 in the isolated `week2/.venv`.

## Automated checks

```bash
cd week2
.venv/bin/python -m pytest -q
```

54 tests pass. Coverage includes:

- Per-person 50-mile intersection, budgets, unknown costs, diet/accessibility requirements and availability.
- Full-visit opening hours, split schedules, overnight periods and conservative holiday handling.
- Deterministic fairness ordering and reproducibility.
- Independent parallel profile execution, verified with a four-party thread barrier.
- Every personal advocate summary reaches the coordinator.
- AI consent, isolated worker inputs and the no-LLM demo path.
- Membership-key hashing, cross-group isolation, complete ballots, edit-in-place voting, vetoes and consensus.
- All-participant confirmation before finalization; owner-only controls and frozen profiles.
- Photo validation, EXIF removal, scoped access, uploader-only deletion and file cleanup.
- Provider response parsing and parameterized Neo4j spatial-query structure using mocks.
- Streamlit landing page, upper-right Help, demo discovery, poll creation, voting, finalized-plan messaging and scrapbook rendering through AppTest.

## Actual external checks

- **Codex CLI:** four fictional personal profiles processed successfully through the existing ChatGPT login; all four person IDs returned. A real coordinator call returned a structured introduction. No real people's profiles or photos were used.
- **Open-Meteo:** a read-only Dallas city-center forecast request returned HTTP 200 with JSON.
- **OpenStreetMap / Overpass:** the default public endpoint returned HTTP 406. Two alternative public endpoints returned HTTP 500 on a small diagnostic request. Live place retrieval is therefore **not verified** in this environment. The adapter parsing is tested with fixtures; failures are visible and no demo catalog is substituted. Manual verified-venue entry is available.
- **Neo4j:** driver installed and query construction tested with mocks. No running database or credentials were provided; a live graph write/query is **not verified**.
- **Google Places / Foursquare:** adapters implemented, but no keys were supplied and account-specific access has **not been verified**.
- **LangSmith / Mem0:** LangSmith tracing was not enabled. Mem0 is not integrated in this version.
- **Reservations:** venue-site handoff only. No real reservation was attempted or made.

## UI and server

The hero image was inspected locally. Functional screens were exercised with Streamlit AppTest. The user requested that the app remain stopped, so no server was launched and no browser screenshot was captured. Responsive styling has not been visually checked in a running browser.

## Repository

Generated databases, uploaded photos, local secrets and virtual environments are ignored. Sample venues and profiles are fictional. No Git commit, push or public deployment was performed.

## Booking SMS addition

Six additional tests cover required booking/coordinator approval, opt-in filtering, once-per-recipient submission, read-only delivery-status refresh, uncertain timeout outcomes, phone isolation from AI profiles, opt-out, and SMS disabled by default. A Streamlit UI test also renders the SMS controls and verifies that pressing Send twice submits only once. All requests are mocked; no real messages were sent and no live Twilio credentials were used. The upper-right Help page and README include setup instructions. The app remains stopped.

## US-wide geography addition

The suite now has **39 passing tests**. Eight additional cases exercise US-only geocoder filtering, state disambiguation, Alaska/Hawaii offline choices, non-Central venue hours and participant availability, daylight-saving gap/fold rejection, timezone-preserving SMS formatting, geography-neutral Google queries, and saving a Seattle profile through Streamlit AppTest. Live requests successfully resolved Portland, Oregon (America/Los_Angeles) and Honolulu, Hawaii (Pacific/Honolulu); results also showed why state disambiguation matters. No personal addresses were used. The local server remains stopped.

## Persistent-group onboarding addition

42 automated tests pass. Additional tests reopen Store instances against the same SQLite directory to prove group and membership persistence, verify organizer-only invitation rotation while preserving existing member keys, and exercise coordinator rejoin plus replacement-invitation UI controls. Personal rejoin and shareable invitation downloads are separate. The upper-right Help and Your group screen include a coordinator/member walkthrough. REFEREE_DATA_DIR optionally selects durable private storage; it does not automatically move an existing database. No invitations or SMS were sent.

## Security hardening review

54 automated tests pass. Read SECURITY_REVIEW.md for concrete findings, mitigations and unresolved public-deployment blockers. Existing local storage was restricted to 0700 directories / 0600 files without deleting groups. Pip was updated to 26.2.1; a fresh pip-audit scan of 69 installed distributions reported no known vulnerabilities. Personal workflow tracing is force-disabled, private media/key downloads avoid the shared media handler, Codex execution features are disabled, invitations expire and member keys can be rotated. Application-encrypted storage and production identity/operational controls are not implemented. This is not an independent penetration-test certification. The existing user-started server was not restarted; the user must restart to clear old in-memory media entries and load config changes.


## October 18: simple ZIP groups

The default flow now supports key-free group setup with a ZIP code and choices,
link-based joining, independent multi-choice preferences and RSVP responses,
persistent storage and owner-only finalization. Text invitation preparation
creates only an SMS application draft; no real messages were sent during tests.
Automated cases cover offline creation, invite URL consumption, new member
identity, expiry, group isolation, finalization restrictions and SMS drafting.
Remote phone hosting is not deployed; localhost security restrictions remain.

Latest local result for the simple-flow change: **69 tests passed**. The 80-second H.264 walkthrough was rebuilt with a synthetic simple-group scenario.

Nearby tiles: 72 automated tests pass, including tile selection into saved group
choices, distance filtering and manual-entry fallback. Live verification on
October 18: Zippopotam.us returned HTTP 200 for 75201; the OpenStreetMap Overpass
endpoint returned HTTP 406 from this environment. Successful live place discovery
could not be verified. No fictional results were substituted. The walkthrough
was regenerated with the new tile flow description.

## October 18: common-ground assistant

78 automated tests pass, including coordinator-only analysis, unanimous opt-in
for relevant responses, omission of names/keys from model inputs, rejection of
unsupported choices, no-common-choice clarification, stale-response rejection
and the recommendation UI without automatic finalization. A live Codex call with
two entirely fictional consenting respondents recommended their shared “Coffee
together” option, returned two follow-up questions, and left the plan unfinalized.
No real member responses were used in that check. The captioned demo was rebuilt.

## October 18: nearby-provider investigation

Reproduced independently of Streamlit with public Dallas ZIP 75201: ZIP lookup
HTTP 200, center 32.7904/-96.8044. Primary Overpass POST timed out; its GET query
returned 502 and even its status endpoint returned nginx 406. Private.coffee
returned HTTP 500 for POST and GET. A further documented Overpass server timed
out. A Photon search returned 403 and was not integrated. Responses do not prove
whether blocking originates at the service or an intermediary; no healthy live
place-response path was established in this environment.

Changes: alternate endpoint handling, bounded requests, failure cooldowns,
stage-specific ZIP errors and HTTP statuses, rejection of server runtime remarks
in HTTP 200 replies, coordinate validation, and invalid ZIP validation before UI
cooldown. Added `scripts/check_nearby.py` for independent reproduction. A real
empty result remains distinct from service failure. **84 automated tests pass**;
mocked failover is verified, but live recovery remains unverified. Manual entry
is available and no synthetic data is substituted.

## October 18: replace simple nearby Overpass dependency

Simple ZIP search now uses Geoapify Places v2; ZIP center lookup remains
Zippopotam.us. The optional advanced Overpass adapter is no longer called by
`referee/nearby.py`. Host credentials are passed only in the Geoapify request
header. Mocked tests verify structured radius/proximity requests, field mapping,
missing/rejected keys, quotas, secret omission, distance filtering and tile choice
selection. **90 tests passed**. No Geoapify key is configured here, so successful
live authenticated place retrieval has not been verified. A generated tutorial
was rebuilt; its synthetic run makes no billable requests.

## October 18: current Dallas demo

The landing-page Dallas demo now runs the simple ZIP/tiles/RSVP experience with
four fictional members, mixed attendance, editable tile selections, role switching,
coordinator-only finalization and an explicitly labeled deterministic sample
recommendation. Headless UI coverage verifies the full path without network or
LLM calls. Texting is disabled and fictional choices have no map links or exposed
member key. 91 tests passed; the 80-second video now exercises this four-member
scenario and all 10 chapter layouts were checked for text overflow.

## October 18: second-stage meetup venue agreement

100 tests pass, including same-page demo search, venue tiles and individual
ballots, persisted rounds, owner-only controls, known-budget exclusion, vetoes,
unanimous Works for me from definite attendees, pending-member completion,
frozen details, restart/reset behavior, AI consent changes, unknown rating/cost
handling, and unsupported model-ID rejection. A live Codex call on entirely
fictional consenting member responses and fictional venue metadata returned a
listed venue ID and left the round in voting status. No real groups were used.
Geoapify remains unconfigured, so live authenticated venue search is still
unverified. The 80-second video exercises the second-stage synthetic venue flow;
all 10 chapter layouts were verified for text overflow.

## October 18: category-specific nearby choice tiles

102 tests passed. New coverage verifies category-to-provider filters, category
cache separation and selected-place retention/clearing while switching categories.
The initial nearby search now has a category selector; its selection basket
combines places across categories for group creation and resets on ZIP change.
The UI search throttle is three seconds; Overpass adapter cooldowns remain
separate and unchanged. GEOAPIFY_API_KEY is absent from both the local .env and
this tool environment, so authenticated live search is still pending host setup.
The captioned walkthrough was rebuilt.

## October 18: photos for the current adventure flow

106 tests pass. A finalized simple venue can now be marked completed by its
coordinator and linked idempotently to the existing private scrapbook. Headless
UI tests verify that completion enables the photo uploader and that a saved
re-encoded image renders in the gallery. A separate UI test records a past
adventure and enables uploads without network calls or venue credentials.
Backend coverage checks coordinator-only completion, group-scoped photo access,
uploader-only deletion and persistence. Existing detailed-planning photo tests
remain intact. The photo form is always visible for completed adventures; an
instructional disabled uploader is shown before completion. The demo video was
rebuilt with the current completion/scrapbook flow.

## October 18: shared-gallery refresh and group departure

114 tests pass. The group gallery is an independently refreshing Streamlit
fragment (five-second interval while the session is active), separate from the
upload form. Headless tests verify another member sees newly saved photos on
rerender and that revoked sessions clear their private view. A live browser's
timer delivery was not separately exercised. Departure tests cover coordinator
transfer, last-member invitation closure, old-key revocation, optional deletion
of only the uploader's memories, preserved shared photos, reset of unfinished
activity/venue votes, and preservation of an already-agreed venue. The video was
rebuilt and all chapter layouts were checked for text overflow.

## October 18: current-workflow page review

117 tests pass. Home, Your group, Our adventures and all four Help tabs now
explain the current activity → venue → coordinator confirmation → shared memories
flow. Older detailed screens are labeled as legacy. README and the synthetic
video use the same workflow, with email authentication, hosting, automated
reservations and simple-flow booking SMS explicitly described as unimplemented.

Personal response budgets are persisted and included in aliased AI input. The
shared spending ceiling uses the proposed event budget and the lowest definite
attendee limit. Tests cover invalid limits, tentative-member handling, zero
budget, persisted UI values across navigation, and rejection of a known venue
cost above an individual limit even after unanimous yes votes. Older responses
inherit the event budget until updated. Unknown costs still require human review.

The 80-second video was rebuilt; all ten chapter text layouts fit. Verification
used headless AppTest and synthetic fixtures; no live provider, browser recording,
reservation or message was performed. No app listener was found on port 8502 and
the app was left stopped.

## October 18: preferences before nearby search

116 tests pass. Group creation no longer renders the nearby category selector or
search action. Members first save activity choices, attendance and budgets;
common-ground analysis waits for every response. Venue search remains below the
response and common-ground sections, after activity agreement, on the same page.
The creation test verifies no premature search or provider call. The reusable
picker's selection-retention test now runs in isolation. Help, README and video
copy were updated to match this ordering. Real AI still requires participant
consent and the host connection; no recommendation automatically finalizes.

## October 18: creator account requirement

119 tests pass. Real event creation now requires a verified Google OIDC identity;
without configured authentication the sign-in button is disabled and explains
host setup. Invitation joining and the fictional demo remain available. Legacy
creation routes now direct to the account-gated current flow.

Accounts are keyed by a hash of canonical issuer and provider subject, not typed
email or display name. SQLite links accounts to created memberships. Tests cover
verified Google claims, stable identity across email changes, cross-account
restore rejection, duplicate-link rejection, restart persistence and departure
revocation. Reopening a saved meetup rotates its membership key, invalidating the
old browser membership session. Sign-out clears the current session.

Authlib and its dependencies were installed and the lock file refreshed. The
Google callback was not exercised live: no Google OAuth credentials are present.
This is creator authentication only; guest invitation membership remains the
prototype access model. Local-only binding remains. The synthetic video was
rebuilt and all ten chapter layouts fit. An existing server was observed on
127.0.0.1:8502; no server was started or stopped during this change.
