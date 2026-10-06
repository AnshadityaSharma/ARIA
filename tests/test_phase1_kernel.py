"""Phase 1 contracts use inert adapters and disposable targets only."""
from dataclasses import dataclass
from unittest.mock import Mock

import pytest

from aria.core import Action, ActionType as T, RISK, Result, Verification
from aria.browser import BrowserManager
from aria.engine import BROWSER_ACTIONS, DISPATCH_ACTIONS, Engine, ExecutionFailed
from aria.permissions import ConfirmationRequired, PermissionDenied, PermissionEngine


@dataclass(frozen=True)
class FakeBrowserTarget:
    url: str
    version: int


class FakeBrowser:
    def __init__(self):
        self.url = "https://local.invalid/form"
        self.version = 1
        self.executed = []
        self.result = Result(True, "adapter acknowledged")

    def capture_target(self, _action):
        return FakeBrowserTarget(self.url, self.version)

    def same_target(self, _action, target):
        return target == self.capture_target(_action)

    def execute_bound(self, action, target, _event):
        if not self.same_target(action, target):
            raise PermissionDenied("Target changed")
        self.executed.append(action)
        return self.result

    def execute(self, action, _event):
        self.executed.append(action)
        return self.result


def pending(engine, action):
    with pytest.raises(ConfirmationRequired) as error:
        engine.execute(action)
    return error.value.pending


def test_registry_and_dispatch_cover_every_action():
    assert set(T) == set(RISK) == set(DISPATCH_ACTIONS)
    assert {T.CLICK_BROWSER_ELEMENT, T.SUBMIT_BROWSER, T.DOWNLOAD_FILE} <= BROWSER_ACTIONS


def test_result_contract_distinguishes_acknowledgement_observation_and_verification():
    acknowledgement = Result(True, "accepted")
    assert not acknowledgement.observed and acknowledgement.verification == Verification.UNVERIFIED
    observed = Result(True, "measured", observed=True)
    assert observed.observed and observed.verification == Verification.UNVERIFIED
    assert Result(True, "checked", observed=True, verification=Verification.VERIFIED).verification == Verification.VERIFIED
    with pytest.raises(ValueError):
        Result(True, "unsupported claim", verification=Verification.VERIFIED)


@pytest.mark.parametrize("result", [Result(False, "executor failed"),
                                      Result(True, "verification failed", verification=Verification.FAILED),
                                      "invalid adapter result"])
def test_executor_and_verification_failures_do_not_report_success(result):
    browser = FakeBrowser()
    browser.result = result
    engine = Engine(browser_factory=lambda: browser, shutdown=Mock())
    with pytest.raises(ExecutionFailed):
        engine.execute(Action(T.OPEN_BROWSER))


def test_invalid_action_never_reaches_adapter():
    browser = FakeBrowser()
    engine = Engine(browser_factory=lambda: browser, shutdown=Mock())
    with pytest.raises(PermissionDenied):
        engine.execute(Action(T.SUBMIT_BROWSER, "Submit", {"role": "css"}))
    assert not browser.executed


@pytest.mark.parametrize("kind", [T.SUBMIT_BROWSER, T.CLICK_BROWSER_ELEMENT, T.DOWNLOAD_FILE])
def test_browser_confirmation_binds_exact_target(kind):
    browser = FakeBrowser()
    policy = PermissionEngine(confirm_low=True)
    engine = Engine(browser_factory=lambda: browser, permissions=policy, shutdown=Mock())
    action = Action(kind, "Submit" if kind != T.DOWNLOAD_FILE else "File")
    request = pending(engine, action)
    assert browser.url in request.description
    browser.version += 1
    with pytest.raises(PermissionDenied, match="Target changed"):
        engine.confirm(request.token)
    assert not browser.executed


def test_browser_confirmation_executes_once_when_target_is_stable():
    browser = FakeBrowser()
    engine = Engine(browser_factory=lambda: browser, shutdown=Mock())
    request = pending(engine, Action(T.SUBMIT_BROWSER, "Submit"))
    result = engine.confirm(request.token)
    assert result.verification == Verification.UNVERIFIED
    assert len(browser.executed) == 1
    with pytest.raises(PermissionDenied):
        engine.confirm(request.token)


def test_browser_without_target_binding_fails_closed():
    browser = Mock(spec=["execute"])
    engine = Engine(browser_factory=lambda: browser, shutdown=Mock())
    with pytest.raises(PermissionDenied, match="cannot be bound"):
        engine.execute(Action(T.SUBMIT_BROWSER, "Submit"))
    browser.execute.assert_not_called()


def test_confirm_low_copy_binds_source_and_destination(tmp_path):
    source = tmp_path / "source.txt"
    source.write_text("data")
    destination = tmp_path / "destination.txt"
    from aria.desktop import Files
    files = Files()
    files.copy = Mock()
    engine = Engine(files=files, permissions=PermissionEngine(confirm_low=True), shutdown=Mock())
    request = pending(engine, Action(T.COPY_PATH, str(source), {"destination": str(destination)}))
    destination.write_text("occupied")
    with pytest.raises((PermissionDenied, FileExistsError)):
        engine.confirm(request.token)
    files.copy.assert_not_called()


def test_confirm_low_folder_binds_parent(tmp_path):
    from aria.desktop import Files
    files = Files()
    files.create_folder = Mock()
    engine = Engine(files=files, permissions=PermissionEngine(confirm_low=True), shutdown=Mock())
    request = pending(engine, Action(T.CREATE_FOLDER, str(tmp_path), {"name": "new"}))
    (tmp_path / "new").mkdir()
    with pytest.raises(PermissionDenied, match="Target changed"):
        engine.confirm(request.token)
    files.create_folder.assert_not_called()


def test_confirm_low_screenshot_binds_absent_output(tmp_path, monkeypatch):
    capture = Mock()
    monkeypatch.setattr("aria.engine.screenshot", capture)
    destination = tmp_path / "shot.png"
    engine = Engine(permissions=PermissionEngine(confirm_low=True), shutdown=Mock())
    request = pending(engine, Action(T.TAKE_SCREENSHOT, str(destination)))
    destination.write_bytes(b"changed target")
    with pytest.raises((PermissionDenied, FileExistsError)):
        engine.confirm(request.token)
    capture.assert_not_called()


def test_browser_adapter_rechecks_same_node_page_and_form_without_playwright():
    class Page:
        url = "https://local.invalid/form"
    class Element:
        def __init__(self):
            self.signature = "form=one"
            self.clicks = 0
        def evaluate(self, script, other=None):
            return self.signature if "JSON.stringify" in script else other is self
        def click(self, **_kwargs):
            self.clicks += 1
    class Locator:
        def __init__(self, element): self.element = element
        def element_handle(self): return self.element
    page = Page()
    element = Element()
    locator = Locator(element)
    browser = BrowserManager()
    browser._require_page = lambda: page
    browser._named = lambda _role, _name: locator
    action = Action(T.SUBMIT_BROWSER, "Submit")
    target = browser.capture_target(action)
    assert browser.same_target(action, target)
    browser.execute_bound(action, target)
    assert element.clicks == 1
    page.url = "https://local.invalid/other"
    assert not browser.same_target(action, target)
    page.url = target.url
    element.signature = "form=two"
    assert not browser.same_target(action, target)
    element.signature = "form=one"
    locator.element = Element()
    assert not browser.same_target(action, target)
