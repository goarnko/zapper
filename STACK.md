# Technology Stack

## Design Principles

The project should prioritize:

- Simplicity
- Native Linux experience
- Zero configuration
- Minimal dependencies
- Fast startup
- Easy packaging
- Long-term maintainability

The application should avoid becoming another media center. Every technology choice should support a lightweight desktop application whose only responsibility is browsing and launching TV channels.

---

# Programming Language

## Python 3.13+

Python is the preferred language because it provides:

- Excellent readability
- Batteries included
- Cross-platform compatibility
- Fast development
- Mature packaging ecosystem

No external runtime should be required beyond a standard Python installation.

---

# GUI Framework

## Tkinter (Initial Release)

Advantages

- Included with Python
- No additional dependencies
- Lightweight
- Native enough on Linux
- Instant startup
- Stable API

Although not the most modern toolkit, it is ideal for an MVP.

---

## Future Option

### PySide6 (Qt)

Potential migration if the project grows.

Advantages

- Modern widgets
- Better layouts
- Better accessibility
- Native dark mode
- Excellent cross-platform support

Disadvantages

- Large dependency
- Bigger binaries
- More complex packaging

Decision:

> Start with Tkinter and only migrate if the project outgrows it.

---

# Media Player

The application **will not implement video playback**.

Instead it delegates playback to an external player.

Supported players:

- VLC (default)
- MPV (future)

The player should be abstracted behind an interface.

Example:

```python
class Player:
    def play(stream_url: str) -> None:
        ...
```

Implementations:

- VLCPlayer
- MPVPlayer

This allows adding new players without affecting the application.

---

# Playlist Format

Supported initially

- M3U
- M3U8

Primary provider

- TDTChannels

Future providers

- Pluto TV
- Samsung TV Plus
- Rakuten TV
- User playlists

The application should never hardcode channels.

Providers are only sources of playlists.

---

# EPG

Supported format

- XMLTV

Downloaded from the configured provider.

Initially:

```
https://www.tdtchannels.com/epg/TV.xml.gz
```

Implementation:

- gzip
- xml.etree.ElementTree

No third-party XML libraries are required.

---

# Storage

Use JSON for user configuration.

Example

```
settings.json
```

```json
{
  "player": "vlc",
  "auto_update": true
}
```

Favorites

```
favorites.json
```

```json
[
  "La 1",
  "La 2",
  "ETB2"
]
```

Recent channels

```
recent.json
```

---

# Cache

Application cache

```
~/.local/share/zaptv/
```

Example

```
playlist.m3u

epg.xml.gz

logos/

cache.db
```

The cache should refresh automatically.

---

# Networking

Python standard library

```
urllib.request
```

No dependency on:

- curl
- wget
- requests

The application should work on a standard Python installation.

---

# Parsing

## Playlist

Custom parser.

M3U is simple enough that external libraries are unnecessary.

Extract:

- channel name
- stream URL
- logo
- tvg-id
- group

---

## EPG

Standard library

```
gzip

xml.etree.ElementTree
```

---

# Desktop Integration

Provide:

- desktop launcher
- icon
- MIME association for M3U playlists (future)

Desktop file:

```
zaptv.desktop
```

---

# Configuration

Configuration should live under

```
~/.config/zaptv/
```

Example

```
settings.json

favorites.json
```

---

# Code Quality

Formatting

- Ruff

Linting

- Ruff

Static typing

- mypy

Testing

- pytest

Package management

- uv

Project configuration

```
pyproject.toml
```

No `requirements.txt`.

---

# Packaging

Initial target

Ubuntu

Future

- Debian
- Linux Mint
- Fedora

Distribution formats

1. AppImage (preferred)
2. Native package
3. Flatpak

Snap support is optional.

---

# Repository Structure

```
zaptv/

├── README.md
├── SPEC.md
├── STACK.md
├── ROADMAP.md
├── LICENSE
├── pyproject.toml
│
├── src/
│   └── zaptv/
│       ├── main.py
│       ├── ui.py
│       ├── player.py
│       ├── playlist.py
│       ├── epg.py
│       ├── updater.py
│       ├── storage.py
│       ├── models.py
│       └── settings.py
│
├── tests/
│
├── assets/
│
└── packaging/
```

---

# External Dependencies

## MVP

None.

Only:

- Python
- VLC

---

# Philosophy

The stack should remain intentionally small.

Every dependency must justify its existence.

If a feature can be implemented using the Python standard library without sacrificing maintainability, that option should be preferred.

The project values simplicity, portability, and maintainability over adopting additional frameworks.
