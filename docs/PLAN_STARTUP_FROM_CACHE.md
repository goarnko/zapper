# PLAN: Open from the cache, refresh in the background

**Status:** done 2026-10-10, all phases verified; awaiting commit approval.
Branch `startup-from-cache`.
**Resume from here:** commit, then merge on approval.

## Motivation

On 2026-10-10 ZapTV showed no window at all, from the terminal or from the
Ubuntu menu. The traceback put it in `socket.create_connection`, inside
`updater.fetch`, called from `providers.load_channels` in `main.main`, which
runs **before the window exists**.

The site was unreachable: `curl -4` to `www.tdtchannels.com` timed out too,
so this is not a Python quirk. The likely cause is Spanish ISPs blocking
Cloudflare ranges during LaLiga matches; that is unconfirmed, and the design
does not depend on it. Slow hotel or train Wi-Fi looks the same to ZapTV.

Why it looked like a permanent hang rather than a 30 s failure:
`www.tdtchannels.com` resolves to **four** addresses (two IPv6, two IPv4).
`create_connection` tries each in turn with the full 30 s timeout, so one
file costs about 2 minutes, and startup fetches the playlist plus up to four
guide feeds. The cache (from 2026-10-08) was perfectly usable the whole time.

**Root cause:** startup treats a refresh as a precondition for showing the
window. `updater.ensure` already falls back to the cache when a download
fails. The problem is only that the fallback comes after the timeouts, and
the timeouts happen with no window.

**The same bug exists after startup.** `ChannelBrowser._reload_channels` and
`reload` (`Ctrl+R`, the playlists window) download on the Tk main thread, so
the open window freezes for the same minutes.

## Decisions

| # | Decision | Why |
|---|---|---|
| 1 | The GUI starts from **caches only**: playlists and guides. No network before the window. | The cache is what the user ends up with anyway when the network fails; this just skips the wait. |
| 2 | Downloading runs on a **daemon thread**. The result comes back on a `queue.Queue` that the UI polls with `after()`. | The same shape as `updates.check_async`, already proven here. A daemon thread never blocks quitting. |
| 3 | The worker **downloads and parses**: playlists into channels, XMLTV into a `Guide`. The main thread only swaps the results in and redraws. | Parsing four guide feeds is too slow for the UI thread. The worker touches no Tk, so it adds no Tk threading risk, and no Pillow either, so the `logos.register_formats` race note does not apply. |
| 4 | `Ctrl+R` and the playlists window **use the same background path**. | It is the same freeze, and one mechanism is simpler than two. |
| 5 | **One refresh at a time.** A request during a running refresh is remembered and runs straight after, with `force` OR-ed in. | Dropping it would lose a provider the user just enabled. Running two at once would race on the cache files. |
| 6 | The connection timeout goes from **30 s to 10 s**. | It now only decides how soon the status bar says "unavailable"; nothing waits on it. `urlopen`'s timeout applies per socket operation, not to the whole download, so a slow but live 3 MB guide is unaffected. |
| 7 | The CLI modes (`--list`, `--search`, `--now`) stay **synchronous**. | With no window there is nothing to show early, and their output must reflect a refresh. |
| 8 | **First launch with no cache:** the window opens empty with "Loading playlists…". If every source fails: "No playlist could be downloaded. Ctrl+R retries." `main` no longer exits with an error for the GUI when it has no channels. | A window explaining the problem beats a terminal message that menu users never see. |
| 9 | When `Settings.auto_update` is off, startup starts no refresh (as today). `Ctrl+R` still works. | This keeps the setting's meaning. |
| 10 | A failed refresh **keeps what is on screen**, for both channels and guide. The status bar names what failed. | This is the existing `_reload_channels` rule ("a dropped network never empties the window"), and it carries over. |

## Target design

### Worker (`refresh.py`, new)

```python
@dataclass(frozen=True)
class Refreshed:
    channels: list[Channel]      # empty when every source failed
    failed: list[str]            # provider names that yielded nothing
    guide: epg.Guide | None      # None when no guide source produced data

def refresh_async(providers: list[Provider], extra: list[tuple[str, str]],
                  force: bool) -> queue.Queue[Refreshed]
```

- `force=False` downloads only stale files (startup, provider toggles), and
  `force=True` downloads everything (`Ctrl+R`), matching today's split
  between `_reload_channels` and `reload`.
- It takes a **snapshot** of the enabled providers, made on the main thread,
  rather than the live `ProviderList`. The playlists window can edit that
  list while the worker runs. The merge in `ProviderList.load_channels` is
  factored so it can run over a given list of providers, without changing
  behaviour.
- Any unexpected exception becomes a `Refreshed` reporting every source as
  failed. The UI never waits forever.

A new module rather than more code in `updater.py` (network primitives) or
`ui.py` (widget wiring), so it can be tested without a display. It is the
same split as `search.py` and `grid.py`.

### UI (`ui.py`)

- `ChannelBrowser.start_refresh(force)` snapshots the providers, calls
  `refresh_async`, sets "Updating playlists…", and polls. If a refresh is
  already running, it records `pending_force |= force` instead.
- On the result: if `channels` is non-empty, swap in `_channels`;
  `_refresh()` (which already preserves the selection and search filter);
  swap in the guide if one came back; `_update_guide()`; then the status
  message. If a refresh is pending, start it.
- `_reload_channels` and `reload` become thin calls to `start_refresh`.
  Their guide-source tracking (`_guide_sources`) moves into the result
  handling.
- `run()` starts the first refresh after the window is built, when
  `config.auto_update` is on.

### Startup (`main.py`)

The GUI path loads channels with `refresh=False` and the guide from cache
(the existing `auto_update`-off branch of `_load_guide`), then calls
`ui.run`. The "No channels from any enabled provider" exit applies only to
the CLI modes.

## Phasing

Each phase ends green on `pytest` (on `:0`, under Xvfb `:99`, and headless),
`ruff` and `mypy`.

1. **`refresh.py` plus the factored merge.** Tests with `updater.fetch`
   stubbed: channels and guide come back on the queue; a failing source is
   listed in `failed`; an exception in the worker still yields a result; the
   snapshot is unaffected by later `ProviderList` edits.
2. **UI.** `start_refresh`, polling, coalescing, the empty-window state.
   Tests (display-dependent): results swap in and keep the selection; a
   failed refresh keeps the list; a second request during a refresh runs
   once afterwards; an empty channel list builds a window. `Ctrl+R` returns
   immediately.
3. **Startup and timeout.** The GUI path in `main.py` uses caches only;
   `_TIMEOUT = 10`. A test that `main` reaches `ui.run` without calling
   `updater.fetch` (both stubbed).
4. **Verify for real.** In a sandboxed `XDG_CONFIG_HOME`/`XDG_DATA_HOME`,
   point a provider at an unroutable address (`http://10.255.255.1/`) to
   reproduce the hang on demand. The window must appear immediately, and
   the status bar must report the failure about 10 s later. Then repeat
   with the real feeds, today while the site is still blocked and again once
   it is back. Capture the window with `xwd` to confirm what the status bar
   says.
   **Result (2026-10-10, sandboxed config/cache, real app on `:0`):** a
   provider at `10.255.255.1` (verified to drop silently) plus the real
   TDTChannels, which was still unreachable. The old code (a `main`
   worktree) showed **no window within 45 s**. The new code showed the
   window in **0.7 s**, populated from a 3-day-old cache, with "Updating
   playlists…", and later "Unavailable: Blackhole". With no cache at all:
   window in 0.7 s showing the 13 local web channels, and later
   "Unavailable: TDTChannels, Blackhole". Captured with `xwd` (extracted
   from `x11-apps`, which is no longer installed here). Not yet repeated
   with TDTChannels reachable.

   **Observed gap, then fixed (user chose to report it):** a source whose
   refresh fails but whose stale cache loads was not named, because
   `updater.ensure` returns the old file as success. `Refreshed.outdated`
   now carries it, and the status bar reads e.g. "Unavailable: Blackhole ·
   TDTChannels not updated since 7 Oct", confirmed in a real capture. The
   status label wraps to the window width so a long report is not cut off
   (the first capture showed it truncated).
5. **Docs.** `CLAUDE.md` (Providers, the update/threading notes, the
   "refresh when >24h" line under Paths); README if it describes startup
   behaviour; a release-notes line in the next tag annotation.

## Out of scope

- Detecting *why* a site is unreachable (LaLiga blocking, IPv6) or working
  around a block.
- Happy-eyeballs / parallel address racing. With the window no longer
  waiting, the cost of trying addresses one by one no longer matters.
- Retrying automatically on a timer. `Ctrl+R` and the next launch are
  enough.
- Showing a cache's age in the UI.
- Reverting your `auto_update = False` workaround. That is your setting;
  switch it back on once this ships.

## Risks / watch-list

- **"No refresh" still downloaded a missing cache (found and fixed in
  Phase 3).** `load_channels(refresh=False)` only skips refreshing a
  *stale* cache; with none at all, `updater.ensure` downloads, so a first
  launch would still have hung with no window. The GUI now uses
  `load_channels(offline=True)` (`Provider.cached()`), which never
  downloads. `refresh=False` keeps its old meaning for the CLI.
- **Selection across a swap (found and fixed in Phase 2).**
  `_restore_selection` matched the previous channel by identity (`is`), and
  a refresh brings new `Channel` objects, so the selection fell back to the
  first row. The old synchronous reload had the same bug, untested. It now
  matches on `(name, group)`, the merge key.
- **Swapping the list under the user.** The refresh can land while they are
  typing a search or have a channel selected. `_refresh` already preserves
  both, which is why it is rebuilt from scratch on every keystroke, but a
  test pins it for this path.
- **Collapsed sections and logos** must survive a swap. `_tick_logos` scans
  rows rather than channels, so new rows get logos, and `collapsed_groups`
  is keyed by label.
- **The guide grid window**, if open, holds the old `Guide` and channel
  list. It keeps showing them until reopened. Acceptable; noted rather than
  solved.
- **Concurrent cache writes.** Coalescing (decision 5) prevents two workers
  at once. A worker killed at quit leaves at most a `.part` file, because
  `download` writes there and renames.
- **A 10 s timeout on a genuinely slow first connection** (satellite,
  captive portal) fails sooner than before. The cache covers it, and
  `Ctrl+R` retries.
