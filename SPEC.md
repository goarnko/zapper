# ZapTV
*A lightweight desktop application to watch Spanish TDT on Ubuntu*

> Companion documents: [STACK.md](STACK.md) for technology decisions,
> [ROADMAP.md](ROADMAP.md) for milestones. Where they disagree with this
> file, they win — they are newer.

## Goal

Build a small, native Linux application that provides the experience we expected from Kodi/IPTV clients, but without the complexity.

The application should focus on one thing:

> Browse and watch Spanish TV channels quickly.

No media center.
No plugins.
No databases.
No complicated configuration.

---

# Motivation

Existing solutions have several problems:

## Kodi

- Overkill for IPTV.
- Difficult configuration.
- PVR plugins.
- Confusing UI.
- Heavy.

## IPTVnator

- Nice interface.
- Embedded browser player often fails.
- EPG configuration is inconsistent between versions.
- Depends on Electron.

## VLC

Excellent player, but:

- No TV-oriented interface.
- Poor channel browsing.
- No favorites.
- No integrated EPG.

---

# Desired UX

Launch:

```
zaptv
```

or click a desktop icon.

The user immediately sees:

```
Spanish TV

★ Favorites
------------------------
La 1
La 2
ETB2

All channels
------------------------
24h
Antena 3
Be Mad
Canal Sur
Clan
Cuatro
...
```

Double-click:

```
La 1
```

↓

VLC opens automatically.

No more steps.

---

# Features

## MVP

- Browse channels
- Search channels
- Favorites
- Open with VLC
- Automatic playlist updates

---

## Nice to have

- Channel logos
- Channel groups
- Recently watched
- Keyboard navigation
- Dark mode
- Sort alphabetically
- Regional filters

---

## Future

Integrated EPG.

Selecting a channel should display:

```
La 1

Now
13:00 Noticias

Next
15:00 Telediario

20:00 Movie
```

without requiring Kodi.

---

# Architecture

```
                TDTChannels
                     │
                     │
         downloads playlist
                     │
                     ▼

              Local cache

      ~/.local/share/zaptv/

            playlist.m3u
            epg.xml.gz
            logos/

                     │

                     ▼

          Python application

                     │

         parses M3U playlist

                     │

         channel objects

                     │

         GUI / Search

                     │

         launches VLC
```

---

# Data source

Official TDTChannels playlist.

Playlist:

https://www.tdtchannels.com/lists/tv.m3u8

EPG:

https://www.tdtchannels.com/epg/TV.xml.gz

The application should never ship channels.

It should always download the latest version.

---

# Tech Stack

## Language

Python 3

Reason:

- Already installed on Ubuntu
- Portable
- Easy packaging
- Huge standard library

---

## GUI

Tkinter

Reasons:

- Included with Python
- Native enough
- No dependencies
- Lightweight
- Fast startup

Alternative:

PySide6

Pros

- Modern widgets
- Beautiful UI

Cons

- Huge dependency
- Packaging complexity

Decision:

Tkinter first.

---

## Player

VLC

Launch using

```
vlc "<stream>"
```

No embedded player.

Let VLC do playback.

---

## Playlist parser

Custom parser.

M3U is simple enough.

Example:

```
#EXTINF:-1 tvg-id="la1" group-title="General",La 1
https://...
```

Extract:

- name
- stream url
- group
- logo
- tvg-id

---

## EPG parser

Python XML parser.

Read

```
epg.xml.gz
```

using

```
gzip
xml.etree.ElementTree
```

No external libraries required.

---

## Storage

JSON

Example:

favorites.json

```json
[
    "La 1",
    "La 2",
    "ETB2"
]
```

settings.json

```json
{
    "vlc_path": "/usr/bin/vlc",
    "auto_update": true
}
```

---

# Directory structure

See [STACK.md](STACK.md) for the authoritative layout. In short:

```
src/zaptv/

    main.py

    ui.py

    playlist.py

    epg.py

    player.py

    updater.py

    storage.py

    settings.py

    models.py

tests/

assets/

packaging/
```

---

# Internal model

```python
Channel

name
streams      # one per mirror; the playlist lists channels repeatedly
logo
group
tvg_id
favorite
```

EPG

```python
Programme

channel
title
start
end
description
```

---

# Updating

At startup:

If playlist older than 24 hours:

Download latest playlist.

Same for EPG.

No user interaction required.

---

# Search

Instant filtering.

Typing

```
cla
```

shows

```
Clan
Classic TV
```

---

# Favorites

Press

```
F
```

or click

⭐

Favorites appear first.

---

# Groups

Examples:

```
General

Regional

Sports

Kids

International
```

---

# Keyboard shortcuts

```
Enter     Play

Ctrl+F    Search

F         Favorite

Ctrl+R    Update

Esc       Clear search
```

---

# Desktop integration

Install

```
tv.desktop
```

Application appears in:

Applications

→ TV

with icon.

---

# Packaging

Target first:

Ubuntu

Future:

- Debian
- Linux Mint
- Fedora

Packaging options:

- Python package
- AppImage
- Flatpak

Avoid Snap unless necessary.

---

# Future roadmap

## v0.1

- Download playlist
- Parse M3U
- Show channels
- Open VLC

---

## v0.2

- Favorites
- Search
- Groups

---

## v0.3

- EPG
- Logos

---

## v0.4

- Channel filtering
- Recently watched
- Settings

---

## v1.0

Stable desktop application.

---

# Non-goals

We are **not** building:

- A media center
- A Kodi replacement
- An IPTV server
- A recorder (PVR)
- A streaming service

This project is simply a **fast launcher for Spanish TV channels**.

---

# Philosophy

The application should follow one principle:

> **Do one thing and do it well.**

Watching TV should take:

```
Launch app

↓

Click channel

↓

Watch TV
```

Everything else should stay out of the user's way.
