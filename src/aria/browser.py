"""Deterministic Playwright browser capabilities with explicit session state."""
from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import re
from urllib.parse import quote_plus, urlparse

from aria.core import Action, ActionType as T, Result
from aria.desktop import Files


ALIASES = {
    "youtube": "https://www.youtube.com/",
    "google": "https://www.google.com/",
    "github": "https://github.com/",
}


class BrowserError(RuntimeError):
    pass


def normalize_url(value: str) -> str:
    value = value.strip()
    if value.casefold() in ALIASES:
        return ALIASES[value.casefold()]
    if "://" not in value:
        value = "https://" + value
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Website must be a valid HTTP or HTTPS URL without credentials")
    if any(ord(char) < 32 for char in value):
        raise ValueError("Website URL contains control characters")
    try:
        parsed.hostname.encode("idna")
        if parsed.port is not None and not 1 <= parsed.port <= 65535:
            raise ValueError
    except (UnicodeError, ValueError) as exc:
        raise ValueError("Website URL has an invalid host or port") from exc
    return value


@dataclass(frozen=True, slots=True)
class BrowserConfig:
    headless: bool = False
    startup_timeout_ms: int = 15_000
    navigation_timeout_ms: int = 20_000
    element_timeout_ms: int = 8_000
    download_timeout_ms: int = 20_000
    downloads_dir: Path | None = None

    def __post_init__(self):
        for name in ("startup_timeout_ms", "navigation_timeout_ms", "element_timeout_ms", "download_timeout_ms"):
            value = getattr(self, name)
            if type(value) is not int or not 100 <= value <= 120_000:
                raise ValueError(f"{name} must be an integer between 100 and 120000")


@dataclass(slots=True)
class BrowserState:
    active: bool = False
    current_url: str | None = None
    last_download: Path | None = None
    last_search: str | None = None


class BrowserManager:
    def __init__(self, config: BrowserConfig | None = None, files: Files | None = None):
        self.config = config or BrowserConfig()
        self.files = files or Files()
        self.state = BrowserState()
        self._playwright = self._browser = self._context = self._page = None

    def start(self, event=lambda _name: None):
        if self._healthy():
            return self._page
        self.close()
        event("browser_start")
        try:
            from playwright.sync_api import sync_playwright
            self._playwright = sync_playwright().start()
            self._browser = self._playwright.chromium.launch(
                headless=self.config.headless, timeout=self.config.startup_timeout_ms)
            self._context = self._browser.new_context(accept_downloads=True)
            self._context.set_default_timeout(self.config.element_timeout_ms)
            self._context.set_default_navigation_timeout(self.config.navigation_timeout_ms)
            self._page = self._context.new_page()
            self.state.active = True
            self.state.current_url = self._page.url
            event("browser_ready")
            return self._page
        except Exception as exc:
            self.close()
            raise BrowserError(f"Browser could not start: {exc}") from exc

    def _healthy(self) -> bool:
        return bool(self._browser and self._browser.is_connected() and self._page and not self._page.is_closed())

    def _require_page(self):
        if not self._healthy():
            self.state.active = False
            self.state.current_url = None
            raise BrowserError("The browser session is unavailable; say 'open browser' to start a new session")
        return self._page

    def _sync_state(self):
        page = self._require_page()
        self.state.active = True
        self.state.current_url = page.url

    def close(self):
        for item in (self._context, self._browser):
            if item is not None:
                try:
                    item.close()
                except Exception:
                    pass
        if self._playwright is not None:
            try:
                self._playwright.stop()
            except Exception:
                pass
        self._playwright = self._browser = self._context = self._page = None
        self.state.active = False
        self.state.current_url = None

    def _navigate(self, url: str, event, *, allow_start: bool = False) -> Result:
        page = self.start(event) if allow_start else self._require_page()
        target = normalize_url(url)
        event("browser_navigation_start")
        try:
            response = page.goto(target, wait_until="domcontentloaded", timeout=self.config.navigation_timeout_ms)
        except Exception as exc:
            raise BrowserError(f"Website did not load within {self.config.navigation_timeout_ms} ms: {target}") from exc
        if response is not None and response.status >= 400:
            raise BrowserError(f"Website returned HTTP {response.status}: {target}")
        self._sync_state()
        event("browser_navigation_complete")
        return Result(True, f"Opened {self.state.current_url}", {"url": self.state.current_url})

    def _named(self, role: str, name: str):
        page = self._require_page()
        locator = page.get_by_role(role, name=re.compile(rf"^{re.escape(name)}$", re.IGNORECASE))
        try:
            locator.first.wait_for(state="attached", timeout=self.config.element_timeout_ms)
        except Exception as exc:
            raise BrowserError(f"Browser element {name!r} ({role}) was not found") from exc
        count = locator.count()
        if count != 1:
            reason = "not found" if count == 0 else "ambiguous"
            raise BrowserError(f"Browser element {name!r} ({role}) is {reason}")
        return locator

    def _type(self, field: str, text: str, event) -> Result:
        page = self._require_page()
        event("browser_interaction_start")
        candidates = (page.get_by_label(field, exact=True), page.get_by_role("textbox", name=field, exact=True),
                      page.get_by_placeholder(field, exact=True))
        combined = candidates[0].or_(candidates[1]).or_(candidates[2])
        try:
            combined.first.wait_for(state="attached", timeout=self.config.element_timeout_ms)
        except Exception as exc:
            raise BrowserError(f"Editable browser field {field!r} was not found") from exc
        matches = [item for item in candidates if item.count() == 1]
        if not matches:
            raise BrowserError(f"Editable browser field {field!r} was not found uniquely")
        matches[0].fill(text, timeout=self.config.element_timeout_ms)
        self._sync_state()
        event("browser_interaction_complete")
        return Result(True, f"Typed into {field}", {"url": self.state.current_url})

    def _click(self, role: str, name: str, event) -> Result:
        event("browser_interaction_start")
        self._named(role, name).click(timeout=self.config.element_timeout_ms)
        self._sync_state()
        event("browser_interaction_complete")
        return Result(True, f"Clicked {name}", {"url": self.state.current_url})

    def _search(self, query: str, youtube: bool, event) -> Result:
        base = "https://www.youtube.com/results?search_query=" if youtube else "https://www.google.com/search?q="
        result = self._navigate(base + quote_plus(query), event)
        self.state.last_search = query
        event("youtube_search_complete" if youtube else "web_search_complete")
        destination = "YouTube" if youtube else "the web"
        return Result(True, f"Searched {destination} for {query}", result.data)

    def _play_youtube(self, query: str, event) -> Result:
        self._search(query, True, event)
        page = self._require_page()
        event("youtube_result_selection_start")
        # YouTube renders results after DOMContentLoaded. Wait for the result
        # contract before enumerating accessible links to avoid a timing race.
        page.locator("a[href*='/watch?v=']").first.wait_for(
            state="attached", timeout=self.config.element_timeout_ms)
        links = page.get_by_role("link")
        candidates = []
        wanted = query.casefold()
        wanted_words = set(re.findall(r"\w+", wanted))
        for index in range(min(links.count(), 250)):
            link = links.nth(index)
            href = link.get_attribute("href") or ""
            if "/watch?v=" not in href:
                continue
            title = (link.inner_text() or link.get_attribute("aria-label") or "").strip()
            words = set(re.findall(r"\w+", title.casefold()))
            score = (len(wanted_words & words) / max(1, len(wanted_words))) + SequenceMatcher(None, wanted, title.casefold()).ratio()
            candidates.append((score, title.casefold(), index))
        if not candidates:
            raise BrowserError("YouTube did not expose any playable results; its page may have changed or require consent")
        score, _title, index = max(candidates)
        if score < .5:
            raise BrowserError(f"No confident YouTube result matched {query!r}")
        try:
            links.nth(index).click(timeout=self.config.element_timeout_ms, no_wait_after=True)
            page.wait_for_url(re.compile(r"youtube\.com/watch"), wait_until="commit",
                              timeout=self.config.navigation_timeout_ms)
            page.locator("video").first.wait_for(state="attached", timeout=self.config.element_timeout_ms)
            self._sync_state()
        except Exception as exc:
            raise BrowserError("YouTube result did not open a playable watch page in time") from exc
        try:
            from playwright.sync_api import expect
            control = page.locator("button.ytp-play-button")
            control.wait_for(state="attached", timeout=self.config.element_timeout_ms)
            title = control.get_attribute("title") or control.get_attribute("aria-label") or ""
            if not title.casefold().startswith("pause"):
                control.click(timeout=self.config.element_timeout_ms)
            # The player toggle changes to Pause only while media is playing.
            expect(control).to_have_attribute("aria-label", re.compile(r"^Pause", re.IGNORECASE),
                                              timeout=self.config.element_timeout_ms)
        except Exception as exc:
            raise BrowserError("YouTube opened the video but playback could not be verified") from exc
        self._sync_state()
        event("youtube_playback_ready")
        return Result(True, f"Playing {query} on YouTube", {"url": self.state.current_url})

    def _download(self, link_name: str, destination: str | None, event) -> Result:
        page = self._require_page()
        link = self._named("link", link_name)
        event("browser_download_start")
        with page.expect_download(timeout=self.config.download_timeout_ms) as info:
            link.click(timeout=self.config.element_timeout_ms)
        download = info.value
        root = self.files.resolve(destination or str(self.config.downloads_dir or "downloads"))
        path = root / Path(download.suggested_filename).name if root.is_dir() else root
        if path.exists():
            raise FileExistsError(f"Download destination already exists: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        download.save_as(path)
        if not path.is_file():
            raise BrowserError("Browser reported a download, but the saved file was not found")
        self.state.last_download = path
        self._sync_state()
        event("browser_download_complete")
        return Result(True, f"Downloaded {path}", {"path": str(path), "url": self.state.current_url})

    def execute(self, action: Action, event=lambda _name: None) -> Result:
        kind = action.kind
        if kind == T.OPEN_BROWSER:
            self.start(event)
            return Result(True, "Browser opened", {"url": self.state.current_url})
        if kind == T.OPEN_WEBSITE: return self._navigate(action.target, event, allow_start=True)
        if kind == T.NAVIGATE_BROWSER: return self._navigate(action.target, event)
        if kind == T.SEARCH_WEB: return self._search(action.target, False, event)
        if kind == T.SEARCH_YOUTUBE: return self._search(action.target, True, event)
        if kind == T.PLAY_YOUTUBE: return self._play_youtube(action.target, event)
        if kind == T.TYPE_IN_BROWSER: return self._type(action.target, action.params["text"], event)
        if kind == T.CLICK_BROWSER_ELEMENT: return self._click(action.params.get("role", "button"), action.target, event)
        if kind == T.SUBMIT_BROWSER: return self._click(action.params.get("role", "button"), action.target, event)
        if kind == T.DOWNLOAD_FILE: return self._download(action.target, action.params.get("destination"), event)
        raise NotImplementedError(kind)
