# KanPlan — Guidance Report
*A living document, updated as we build each phase.*

---

## Phase 1 — Foundation (✅ Built)

### What was built
- Flask app factory (`app.py`) with blueprints for auth, dashboard, board
- Postgres-ready schema via SQLAlchemy: `User`, `Workspace`, `WorkspaceMember`, `Board`, `Task`, `ActivityLog`
- Google OAuth login (Authlib) with session handling via Flask-Login
- On first login: auto-creates a personal Workspace + default Board + Admin membership
- Base UI shell (sidebar, dashboard stat cards, Kanban board with drag & drop via SortableJS) using the color palette you approved
- Verified: all files compile, and the app boots end-to-end against a test SQLite DB with all routes registering correctly

### Why these choices
- **Postgres over SQLite**: agreed earlier — SQLite doesn't handle concurrent writes well with a multi-user team, Postgres does.
- **Workspace → Board → Task hierarchy**: lets the app support shared team boards, not just private per-user lists, without a full redesign later.
- **Admin / Member roles** (not a granular matrix): matches your actual team size (5), avoids over-engineering.
- **ActivityLog table**: lightweight audit trail so "who changed what" is answerable without heavy tooling.

### Things YOU need to do (I can't do these — they require your accounts/credentials)

**1. Create a Postgres database (pick one, all have free tiers):**
- [Supabase](https://supabase.com) — recommended, has a UI to browse your data too
- [Neon](https://neon.tech) — serverless, scales to zero when idle
- [Railway](https://railway.app)

After creating a project, copy the connection string — it looks like:
`postgresql://user:password@host:5432/dbname`

**2. Set up Google OAuth credentials:**
1. Go to [Google Cloud Console](https://console.cloud.google.com/) → create a new project (e.g. "KanPlan")
2. Go to **APIs & Services → OAuth consent screen** → choose "External" (or "Internal" if you're on Google Workspace) → fill in app name, your email
3. Go to **APIs & Services → Credentials → Create Credentials → OAuth Client ID**
   - Application type: **Web application**
   - Authorized redirect URI: `http://localhost:5000/login/google/callback` (add your production URL later too)
4. Copy the **Client ID** and **Client Secret**

**3. Fill in your `.env` file:**
Copy `.env.example` to `.env` and paste in:
- `DATABASE_URL` (from step 1)
- `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` (from step 2)
- `FLASK_SECRET_KEY` — any long random string (e.g. run `python3 -c "import secrets; print(secrets.token_hex(32))"`)

### How to run it locally
```bash
cd kanplan
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # then fill in real values
python3 app.py
```
Visit `http://localhost:5000/login` — click "Continue with Google."

### Known trade-offs / things deferred on purpose
- "Add Task" button currently shows a placeholder alert — the real modal form is Phase 2.
- Only one board is auto-created per workspace; multi-board UI comes later if needed.
- No Google Sheets export yet — that's Phase 5, and will be on-demand/scheduled per our earlier agreement (not synchronous per-click, to avoid API rate-limit issues).
- `db.create_all()` is used for dev convenience. Before this goes anywhere near production, we should switch to Flask-Migrate so schema changes don't risk data loss.

---

## Phase 2 — Core Kanban (✅ Built)

### What was built
- **Add Task modal**: title, description, priority, status, due date, tags — replaces the Phase 1 placeholder button
- **Edit Task modal**: click any card to open it pre-filled with that task's data
- **Delete**: available inside the Edit modal, with a confirm prompt before deleting
- **Search bar**: filters cards live by title, description, and tags as you type
- **Filters**: dropdowns for Status, Priority, and Due (Today / Overdue) — combine with search, all client-side for instant results
- Column counts update live as filters/search narrow down visible cards
- Verified: booted the app, logged in a test user via the database directly, rendered `/board`, and created a task through the API — all returned correct responses

### Why these choices
- Search/filtering is done **client-side in JavaScript**, not via new API calls — with a small team (5 people) the number of tasks on screen at once is small enough that this is instant and avoids extra server round-trips. If task volume grows a lot later, this can move server-side without changing the UI.
- After Add/Edit/Delete, the page does a full reload rather than live DOM patching — simpler and more reliable for v1; can be made more "SPA-like" later if it feels sluggish.
- Assignee picker was intentionally left out of this Add/Edit modal — per the roadmap, real teammate assignment belongs in Phase 3 once workspace invites exist. Right now new tasks are unassigned until Phase 3.

### Known setup gotcha (for future reference)
On macOS, port 5000 is often taken by the AirPlay Receiver, causing local dev servers to seem broken even when they're running fine. Two fixes: turn off AirPlay Receiver in System Settings → General → AirDrop & Handoff, or just run Flask on a different port (e.g. 8000) and update `APP_BASE_URL` in `.env` plus the authorized origins/redirect URIs in Google Cloud to match.

### How to see it
Pull the updated project, restart the Flask server (`Ctrl+C` then `python app.py`), and go to `/board`. Click "+ Add Task" or click any existing card to try the new modal.

---

## Phase 3 — Team layer (✅ Built)

### What was built
- **New Team page** (`/team`) — lists all current members with their role (Admin/Member), plus any pending invites
- **Invite flow**: click "+ Invite" on the Team page, enter a Gmail address. This creates a pending `Invite` record. The next time that email logs in via Google, they automatically join *your* workspace instead of getting their own new one.
- **Activity log panel**: opening any existing task (via Edit) now shows a running history of who created, edited, moved, or deleted it, newest first
- Verified end-to-end: simulated an admin sending an invite, a new user logging in with that exact email, and confirmed they landed in the *same* workspace as the admin (not a separate one) — this was the trickiest part to get right and it's tested, not just assumed working

### A real bug caught during testing (and fixed before packaging)
The `ActivityLog` table had a `user_id` column from Phase 1, but was missing the actual SQLAlchemy relationship needed to fetch the `User` object from a log entry. This would have caused a server error the first time anyone opened a task's activity panel. Caught by an automated test before this ever reached you — fixed in `database/models.py`.

### Important manual step this phase depends on
Sending an invite in KanPlan does **not** automatically add someone to your Google OAuth "test users" list — those are two separate systems. If you invite a teammate's email in KanPlan but haven't also added them as a test user in Google Cloud Console (Audience → Test users), their Google login will still be blocked with an access error, even though the invite exists correctly in KanPlan. The Invite modal has a note reminding you of this, but it's worth doing both steps together.

### Known trade-off
Invites are matched by email only — if someone's actual Google account email differs even slightly from what you typed (typo, different Google account than expected), they won't auto-join and you'd need to check and resend. No verification/confirmation email is sent in this version — it's a simple, low-overhead system appropriate for a 5-person team, not a full invite pipeline.

### How to see it
Click "Team" in the sidebar (new nav item, between Board and Analytics). Try inviting a second Gmail address you control to see the full loop.

## Phase 4 — Dashboard & Analytics (✅ Built)

### What was built
- **New Analytics page** (`/analytics`, sidebar link now works — was a placeholder `#` before)
- **Task Status Distribution** — doughnut chart across all 5 columns
- **Weekly Completed Tasks** — bar chart, last 7 days, one bar per day
- **Monthly Completed Tasks** — bar chart, last 6 months, one bar per month
- **Per-Person Breakdown** — table showing each team member's total tasks, completed count, and productivity %, sorted by workload. Includes an "Unassigned" row for tasks with no owner.
- Verified with real test data across two people and unassigned tasks — the math (completed/total, sorting, monthly bucketing) was checked against hand-calculated expected values, not just "does it render"

### How completion is tracked
Weekly/monthly charts use each task's `updated_at` timestamp as a proxy for "when it was completed" — there's no separate "completed_at" field. In practice this is accurate as long as a task's last edit was the move to Completed, which is the normal flow. If someone edits a completed task's description weeks later, that would (harmlessly) shift its "completed" bar to that later date. Worth knowing, not worth fixing yet at this scale.

### How to see it
Click "Analytics" in the sidebar.

---

## Phase 5 — Sheets export & Settings (✅ Built)

### What was built
- **Settings page** (`/settings`, sidebar link fixed) — Profile info, theme toggle, Export CSV, Sync Now
- **Theme toggle**: Light/Dark, saved per-user in the database, applies across every page (not just Settings) via a `data-theme` attribute — tested end-to-end including that it persists and applies correctly on reload
- **CSV export**: downloads all your workspace's tasks as `kanplan_tasks.csv` — fully tested, includes owner names and timestamps
- **Google Sheets sync ("Sync Now")**: creates a Google Sheet on first sync, reuses the same sheet on every sync after that (updates in place rather than creating duplicates)

### ⚠️ Important: what's tested vs. what needs YOUR verification
Everything else in this project has been tested end-to-end in a sandbox before being handed to you. **Google Sheets sync is the one exception** — it requires live Google OAuth credentials I don't have access to here. What I did instead:
- Tested all the logic thoroughly using simulated (mocked) Google API responses — token refresh, sheet creation, sheet reuse on repeat syncs, correct data formatting, and error handling all pass
- Followed Google's official Sheets API v4 documentation exactly for the real HTTP calls

**What this means for you**: the code is well-tested at the logic level, but the *very first real sync* is the actual proof it works end-to-end. Please try it and tell me what happens — if Google's API responds differently than documented, we'll fix it together.

### A required manual step before Sync Now will work at all
This phase needed a new Google permission (`spreadsheets` scope) that your existing login doesn't have. **You (and anyone on the team who wants to use Sync Now) must log out and log back in once** — this re-triggers Google's consent screen, this time asking for Sheets access too. Until you do this, clicking "Sync Now" will show a clear error message telling you to re-login, rather than crashing.

### One more Google Cloud step
Go to Google Cloud Console → APIs & Services → Library → search "Google Sheets API" → click **Enable** (if not already enabled on your project). Without this, Sheets API calls will fail even with the right permissions granted.

### Known trade-off (as originally agreed)
Sync is on-demand (click "Sync Now"), not automatic per-action — this was a deliberate decision made early on to avoid Google Sheets API rate limits under real use. If you want it more automatic later (e.g. a background sync every few minutes), that's a small addition on top of this foundation, not a rebuild.

### How to see it
Click "Settings" in the sidebar. Try the theme toggle first (fully safe, instant). For Sheets sync: log out, log back in, then click "Sync Now" and let me know what happens.

---

## Permissions & Archive model (✅ Built)

### What was built
Per your call: everyone in a workspace can **view** all cards, but **edit/move/archive** is restricted to the task's creator, its current assignee, or an admin. **Permanent delete is admin-only** — everyone else archives instead (soft-delete: hidden from the board, kept in the database for audit/recovery).

- Enforced on the **server**, not just hidden in the UI — tested with 12 separate checks covering every role × action combination (a "bystander" member gets a clean 403 on edit/move/archive/delete but can still view; the owner can edit/move/archive their own task but not permanently delete it; an admin can do everything, including delete)
- View-only cards show a small 🔒 badge and can't be dragged
- Opening a view-only task shows all fields locked/greyed out with a note explaining why, rather than silently failing
- A warm, time-of-day-aware welcome note was also added to the top of the Dashboard

### ⚠️ Database migration needed (same pattern as last time)
This adds one new column: `tasks.archived`. Same issue as the Google Sheets fields earlier — `db.create_all()` won't add it to your already-existing table automatically. Run this in Supabase SQL Editor before restarting the app:

```sql
ALTER TABLE tasks ADD COLUMN IF NOT EXISTS archived BOOLEAN DEFAULT FALSE;
```

### Archived tasks are now browsable
There's now a **"🗄️ Archived (N)"** link on the Board page (only appears when there's at least one archived task) that takes you to a full list of everything archived, with a **Restore** button for anyone allowed to edit that task (creator, assignee, or admin). Everyone else can still see archived tasks in that list, just without the ability to restore them — consistent with the view-only rule everywhere else. Tested end-to-end: archive → appears in list → restore → reappears back on the board, plus confirmed a non-owner correctly can't restore someone else's archived task.

---

## Phase 6a — Team member removal & Convo chat (✅ Built)

### What was built
- **Remove member** — on the Team page, admins now see a "Remove" button next to every other member. Removes them from the workspace (boards, tasks, chat) immediately. Admins can't remove themselves (prevents accidentally locking yourself out) — enforced server-side, not just hidden in the UI. Tested: non-admin gets 403, self-removal gets 400, admin removing a teammate returns 204 and the membership row is actually deleted.
- **Convo (chat)** — new `/convo` page using **Stream Chat** (free tier), reusing your existing "Convo" nav item that was previously a disabled "Soon" placeholder:
  - **1-on-1 DMs**: click any teammate in the sidebar to open/create a direct chat
  - **Group channel**: one auto-created channel per Workspace ("Team chat") — every member sees the same one, no manual setup
  - **Auto-sync with Team membership**: joining a workspace (signup or accepted invite) auto-adds you to its Team chat channel; being removed via the new "Remove" button auto-removes you from it too — chat access always matches workspace access, nothing to manage twice
  - Video calling was intentionally left out of this phase — Stream Video is a separate SDK in the same family, so it plugs into these same users/channels later without rework

### Why these choices
- **Stream Chat over building from scratch**: chat infrastructure (real-time delivery, message storage, presence) is weeks of work to build correctly; Stream's SDK handles it, and their free tier covers a 5-person team comfortably.
- **Deterministic DM channel IDs** (`dm-{userA}-{userB}`, sorted): re-opening a chat with the same person always reuses the same channel instead of creating duplicates.
- **Best-effort chat sync, not hard-blocking**: if Stream isn't configured yet (`.env` not filled in) or a network call to Stream fails, workspace membership changes (the part that actually matters for security/access) still succeed — chat sync is wrapped in try/except so it never blocks the core action. The Convo page itself shows a clear "not set up yet" message with a link to getstream.io instead of erroring, matching the same deferred-setup pattern used for Google Sheets sync in Phase 5.
- **Custom vanilla-JS chat UI, not `stream-chat-react`**: KanPlan's frontend is server-rendered Jinja + vanilla JS, not React, so the integration uses Stream's lower-level JS client (`stream-chat` npm package via CDN) directly rather than their React component library — kept intentionally simple (message list + input), not a full-featured chat UI (no read receipts, typing indicators, or file attachments in this pass).

### Manual setup step required before Convo will work
**1. Create a free Stream account:**
1. Go to [getstream.io](https://getstream.io) → sign up → create a new app (any name, e.g. "KanPlan")
2. In the app dashboard, copy the **API Key** and **API Secret**

**2. Add to your `.env`:**
```
STREAM_API_KEY=your_key_here
STREAM_API_SECRET=your_secret_here
```

**3. Restart the app.** That's it — no database migration needed for this phase (Stream stores chat data on their side, not in your Postgres DB). Existing team members will get added to the Team chat channel automatically the next time they log in (since the sync happens in the login flow). If you want everyone added immediately without waiting for their next login, let me know and I can add a one-time backfill script.

### Verified before packaging
- App boots end-to-end with Stream **not** configured — `/convo` shows a graceful setup message instead of crashing, confirming existing users aren't broken by this change before you've added your Stream keys
- `/team` page renders the new Remove button correctly for admins only
- Full permission matrix tested: non-admin attempting removal → 403, admin attempting self-removal → 400, admin removing a teammate → 204 and the membership row is actually gone from the database (not just hidden)
- Real Stream API calls (creating channels, sending/receiving messages) are **not** yet verified against a live Stream account — same caveat as Google Sheets sync in Phase 5: the logic follows Stream's documented API exactly, but the first real login + first real message is the actual end-to-end proof. Please try it after adding your keys and let me know what happens.

### Known trade-offs (deferred on purpose)
- Existing members only join the Team chat channel on their *next* login, not retroactively — acceptable for a 5-person team where everyone logs in daily anyway
- No unread-message badges or notifications yet — Convo is pull-based (you check it), not push
- No message editing/deleting, file attachments, or typing indicators — kept to the essentials for v1

---

## Phase 6b — Video calling (⏳ Not started)
Stream Video SDK, reusing the same users/channels set up in Phase 6a. Next up whenever you're ready.

## Phase 7 — Polish & scale-readiness (⏳ Not started)
Light polling for near-real-time board updates, DB indexing pass, mobile responsiveness pass.
