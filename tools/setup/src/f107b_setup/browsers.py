"""Checkpoint 7 — the default browser.

Two release-wide decisions constrain this screen, and both are structural
rather than cosmetic:

* **Every browser offered comes from Debian main.** The browser question is
  therefore the one screen in setup that grants no third-party APT trust at
  all, and it must stay that way: a Google-archive Chrome entry here would
  smuggle a standing root-equivalent trust grant into a question the operator
  reads as a preference.
* **Skipping leaves a working handler.** ``chromium`` is the shipped default,
  so no configuration reachable through this screen — including declining it —
  leaves the machine without a link handler.

``chawan`` ships as a deliberate terminal surface and is never a default
handler, so it is not in the offer list.
"""

from __future__ import annotations

from dataclasses import dataclass

#: The association surfaces a default must be written through. All three, or
#: the choice is only half made and a desktop launcher disagrees with a CLI.
ASSOCIATION_SURFACES = (
    "alternatives:x-www-browser",
    "alternatives:gnome-www-browser",
    "xdg-settings:default-web-browser",
    "mimeapps:x-scheme-handler/http",
    "mimeapps:x-scheme-handler/https",
    "mimeapps:text/html",
)

SHIPPED_DEFAULT = "chromium"

#: Never a default handler, whatever else it is.
NEVER_DEFAULT = frozenset({"chawan"})


@dataclass(frozen=True)
class BrowserChoice:
    browser_id: str
    label: str
    #: Debian component. Anything but ``main`` is refused by ``offer``.
    component: str
    #: Whether it is installed already or needs a lazy fetch from the snapshot.
    installed: bool


CANDIDATES: tuple[BrowserChoice, ...] = (
    BrowserChoice("chromium", "Chromium", "main", True),
    BrowserChoice("firefox-esr", "Firefox ESR", "main", False),
)


class BrowserRefusal(ValueError):
    """The requested browser will not be offered or set."""


def offer() -> tuple[BrowserChoice, ...]:
    """The offer list, refusing anything outside Debian main."""

    for candidate in CANDIDATES:
        if candidate.component != "main":
            raise BrowserRefusal(
                f"{candidate.browser_id} is in {candidate.component!r}, not Debian main; "
                "the browser question grants no third-party trust"
            )
        if candidate.browser_id in NEVER_DEFAULT:
            raise BrowserRefusal(f"{candidate.browser_id} is never a default handler")
    return CANDIDATES


def resolve(selection: str | None) -> tuple[str, tuple[str, ...]]:
    """Resolve a choice into ``(browser_id, surfaces to write)``.

    ``None`` means the operator skipped the question, which resolves to the
    shipped default and writes nothing: the handler already works.
    """

    if selection is None:
        return SHIPPED_DEFAULT, ()
    if selection in NEVER_DEFAULT:
        raise BrowserRefusal(f"{selection} is never a default handler")
    valid = {candidate.browser_id for candidate in offer()}
    if selection not in valid:
        raise BrowserRefusal(f"{selection!r} is not an offered browser")
    return selection, ASSOCIATION_SURFACES
