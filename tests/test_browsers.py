"""Browser discovery and launching.

Everything here runs against desktop entries written into tmp_path, never
the machine's own: CI runners have no browsers at all, and this machine's
are snaps that a test must not depend on.
"""

import shutil
import subprocess
from pathlib import Path

from zaptv import browsers
from zaptv.player import BrowserPlayer

FIREFOX = """[Desktop Entry]
Type=Application
Name=Firefox
Name[es]=Navegador Firefox
Exec=/snap/bin/firefox %u
Categories=GNOME;GTK;Network;WebBrowser;
MimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;

[Desktop Action new-private-window]
Name=New Private Window
Exec=/snap/bin/firefox --private-window %u
"""

OPERA = """[Desktop Entry]
Name=Opera
Exec=/snap/bin/opera %U
Categories=Network;WebBrowser;
MimeType=text/html;x-scheme-handler/http;x-scheme-handler/https;
"""

#: A media player claims stream schemes but is not a browser.
VLC = """[Desktop Entry]
Name=VLC media player
Exec=/usr/bin/vlc --started-from-file %U
Categories=AudioVideo;Player;Recorder;
MimeType=video/mp4;x-scheme-handler/rtsp;x-scheme-handler/mms;
"""


def _apps(directory, **entries):
    directory.mkdir(parents=True, exist_ok=True)
    for name, text in entries.items():
        (directory / f"{name}.desktop").write_text(text, encoding="utf-8")
    return directory


def test_finds_browsers_and_ignores_other_handlers(tmp_path):
    apps = _apps(tmp_path / "apps", firefox_firefox=FIREFOX, opera_opera=OPERA, vlc=VLC)
    found = browsers.installed([apps])
    assert [(b.id, b.name) for b in found] == [
        ("firefox_firefox.desktop", "Firefox"),
        ("opera_opera.desktop", "Opera"),
    ]


def test_actions_and_localised_names_do_not_leak_into_the_entry(tmp_path):
    apps = _apps(tmp_path / "apps", firefox=FIREFOX)
    (firefox,) = browsers.installed([apps])
    assert firefox.name == "Firefox"
    assert firefox.exec == "/snap/bin/firefox %u"


def test_the_category_alone_is_not_enough(tmp_path):
    """A 'WebBrowser' entry that opens no web links would launch nothing."""
    helper = FIREFOX.replace("x-scheme-handler/http;x-scheme-handler/https;", "")
    assert browsers.installed([_apps(tmp_path / "apps", helper=helper)]) == []


def test_hidden_and_nodisplay_entries_are_skipped(tmp_path):
    apps = _apps(
        tmp_path / "apps",
        hidden=OPERA + "Hidden=true\n",
        nodisplay=OPERA.replace("[Desktop Entry]\n", "[Desktop Entry]\nNoDisplay=true\n"),
    )
    assert browsers.installed([apps]) == []


def test_a_users_override_wins_over_the_system_copy(tmp_path):
    """Per the spec the first directory owns an id — including to hide it."""
    user = _apps(tmp_path / "user", opera=OPERA.replace("[Desktop Entry]\n",
                                                        "[Desktop Entry]\nHidden=true\n"))
    system = _apps(tmp_path / "system", opera=OPERA, firefox=FIREFOX)
    assert [b.name for b in browsers.installed([user, system])] == ["Firefox"]


def test_entries_in_subdirectories_use_dashed_ids(tmp_path):
    _apps(tmp_path / "apps" / "kde", falkon=OPERA.replace("Opera", "Falkon"))
    (falkon,) = browsers.installed([tmp_path / "apps"])
    assert falkon.id == "kde-falkon.desktop"


def test_a_missing_tryexec_hides_the_entry(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _name: None)
    apps = _apps(tmp_path / "apps", gone=OPERA + "TryExec=opera-gone\n")
    assert browsers.installed([apps]) == []


def test_missing_directories_are_not_an_error(tmp_path):
    assert browsers.installed([tmp_path / "absent"]) == []


def test_application_dirs_follow_xdg(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "home"))
    monkeypatch.setenv("XDG_DATA_DIRS", "/a:/b:/a")
    assert browsers.application_dirs() == [
        tmp_path / "home" / "applications",
        Path("/a/applications"),
        Path("/b/applications"),
    ]


# -- Exec field codes ----------------------------------------------------


def _args(exec_line, url="https://www.tf1.fr/tf1/direct"):
    return browsers.Browser("x.desktop", "X", exec_line).args(url)


def test_url_codes_take_the_url():
    url = "https://www.tf1.fr/tf1/direct"
    assert _args("/snap/bin/firefox %u") == ["/snap/bin/firefox", url]
    assert _args("/snap/bin/opera %U") == ["/snap/bin/opera", url]


def test_other_codes_are_dropped_and_percent_is_literal():
    assert _args("browser --icon %i --name %c --flag=100%% %u")[-2:] == [
        "--flag=100%",
        "https://www.tf1.fr/tf1/direct",
    ]
    assert "%i" not in _args("browser %i %u")


def test_an_exec_without_a_url_code_gets_it_appended():
    assert _args("env FOO=1 /usr/bin/browser") == [
        "env", "FOO=1", "/usr/bin/browser", "https://www.tf1.fr/tf1/direct",
    ]


def test_quoted_paths_stay_one_argument():
    assert _args('"/opt/My Browser/run" %u')[0] == "/opt/My Browser/run"


# -- launching -----------------------------------------------------------


def test_the_chosen_browser_is_launched_directly(monkeypatch):
    opera = browsers.Browser("opera_opera.desktop", "Opera", "/snap/bin/opera %U")
    monkeypatch.setattr(browsers, "find", lambda id_: opera if id_ == opera.id else None)
    spawned = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **_kw: spawned.append(argv))

    BrowserPlayer("opera_opera.desktop").play("https://www.bbc.co.uk/iplayer/live/bbcone")
    assert spawned == [["/snap/bin/opera", "https://www.bbc.co.uk/iplayer/live/bbcone"]]


def test_an_uninstalled_choice_falls_back_to_the_desktop_default(monkeypatch):
    monkeypatch.setattr(browsers, "find", lambda _id: None)
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    spawned = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **_kw: spawned.append(argv))

    BrowserPlayer("opera_opera.desktop").play("https://www.tf1.fr/tf1/direct")
    assert spawned == [["/usr/bin/xdg-open", "https://www.tf1.fr/tf1/direct"]]


def test_no_choice_means_the_desktop_default(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}")
    spawned = []
    monkeypatch.setattr(subprocess, "Popen", lambda argv, **_kw: spawned.append(argv))

    BrowserPlayer().play("https://www.tf1.fr/tf1/direct")
    assert spawned == [["/usr/bin/xdg-open", "https://www.tf1.fr/tf1/direct"]]


def test_system_default_reads_xdg_settings(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _n: "/usr/bin/xdg-settings")
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a, 0, "firefox_firefox.desktop\n", ""),
    )
    assert browsers.system_default() == "firefox_firefox.desktop"


def test_system_default_without_xdg_settings_is_unknown(monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _n: None)
    assert browsers.system_default() is None
