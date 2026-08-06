# Roadmap

## Vision

ZapTV should become the simplest way to browse and watch live television on Linux.

The application should remain focused on a single workflow:

```
Open application

↓

Select channel

↓

Watch TV
```

Everything else is secondary.

---

# Milestone 1 — Foundation (MVP)

Goal:

Watch television with the minimum possible functionality.

## Features

- Project skeleton
- Settings management
- Playlist download
- Playlist parsing
- Channel model
- Channel list
- Launch VLC
- Manual refresh

Deliverable

```
Working desktop application capable of browsing
channels from TDTChannels and opening them in VLC.
```

---

# Milestone 2 — Better Browsing

Goal:

Make channel discovery pleasant.

## Features

- Search
- Instant filtering
- Channel groups
- Alphabetical sorting
- Favorites
- Recent channels

Deliverable

```
Fast navigation through hundreds of channels.
```

---

# Milestone 3 — TV Guide

Goal:

Integrate program information.

## Features

- Download XMLTV
- Parse EPG
- Current programme
- Next programme
- Programme details
- Refresh EPG

Deliverable

```
Users can see "Now" and "Next"
without leaving the application.
```

---

# Milestone 4 — Polish

Goal:

Feel like a native desktop application.

## Features

- Channel logos
- Better icons
- Improved layout
- Keyboard shortcuts
- Dark mode
- Settings window

Deliverable

```
Feature-complete desktop experience.
```

---

# Milestone 5 — Multiple Providers

Goal:

Support more than one playlist source.

## Features

- Provider abstraction
- User playlists
- Multiple playlists
- Playlist management
- Merge channels

Supported providers

- TDTChannels
- Custom M3U
- Pluto TV (where legally available)

## Note — Atresmedia and Mediaset

Antena 3, laSexta, Neox, Nova, Mega, Atreseries, Telecinco, Cuatro, FDF,
Energy, Divinity, Boing and Be Mad are missing from the channel list.

They are absent from the TDTChannels playlist because both broadcasters
gate live playback behind their own platforms (Atresplayer, Mitele). The
XMLTV guide *does* carry them, so they already appear as programme data
with no stream to play.

This milestone supplies the plumbing: pointing ZapTV at a list that
carries working URLs for them is enough. If no such list exists, they
instead need a player that can open the broadcaster's web player — see
Milestone 6.

Deliverable

```
ZapTV becomes a general IPTV browser.
```

---

# Milestone 6 — Player Improvements

Goal:

Player independence.

## Features

- VLC backend
- MPV backend
- Player selection
- Player detection

A browser backend belongs here too, if the Atresmedia and Mediaset
channels noted under Milestone 5 turn out to need one: opening the
broadcaster's web player is a player choice, not a playlist source.

Deliverable

```
Playback works with multiple media players.
```

---

# Milestone 7 — Packaging

Goal:

Easy installation.

## Features

- AppImage
- Debian package
- Desktop integration
- Icons
- Automatic updates (application)

Deliverable

```
Install and run with no manual configuration.
```

---

# Milestone 8 — Quality

Goal:

Project maturity.

## Features

- Unit tests
- Integration tests
- CI
- Documentation
- Type checking
- Linting

Deliverable

```
Production-quality open source project.
```

---

# Stretch Goals

Potential future features.

## Watch history

Remember recently viewed channels.

---

## Recording

Allow VLC or MPV to record streams.

---

## Notifications

Notify when favourite programmes begin.

---

## Plugins

Support external playlist providers.

---

## Chromecast

Send playback to Chromecast.

---

## Remote Control

Simple HTTP API.

---

## Mobile Companion

Browse channels from a phone.

---

# Out of Scope

The project intentionally avoids becoming another Kodi.

Not planned:

- Media library
- Movies
- TV series
- Music
- PVR backend
- Torrent support
- Streaming server
- User accounts
- Cloud synchronisation

---

# Success Criteria

The project is successful if a new user can:

1. Install ZapTV.
2. Launch it.
3. Click a channel.
4. Watch TV.

...within two minutes, without reading documentation.

That experience is the guiding principle behind every feature and design decision.
