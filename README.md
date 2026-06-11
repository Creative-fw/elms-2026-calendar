# ELMS 2026 - Auto-Updating Apple Calendar Feed

Daily sync from europeanlemansseries.com's official calendar endpoints with
their timezone bug repaired (Paris double-converted end times - including
the western variant where Silverstone/Portimao sessions end before they
start). Round-level consistency vote makes corrections self-healing in both
directions.

## Subscribe (Apple Calendar)

**iPhone:** Settings > Apps > Calendar > Calendar Accounts > Add Account >
Other > Add Subscribed Calendar:

    https://raw.githubusercontent.com/Creative-fw/elms-2026-calendar/main/ELMS_2026.ics

**Mac:** Calendar > File > New Calendar Subscription > same URL.
Set Auto-refresh: Every day. Choose location iCloud so it syncs to all
devices and refreshes server-side.

## How updates flow

ELMS changes a session time -> GitHub Action picks it up daily at 03:15 UTC
(07:15 Dubai) -> commits new ICS -> Apple Calendar pulls on next refresh.

During a live race week, trigger the Action manually (Actions tab >
Run workflow) for an instant sync.

Sister feed: [FIA WEC 2026](https://github.com/Creative-fw/wec-2026-calendar)
