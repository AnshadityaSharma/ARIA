import json
import time
from pathlib import Path
from unittest.mock import Mock

import pytest
from aria.core import ActionType as T, Rect
from aria.engine import Engine
from aria.intent import Interpreter, IntentError, decode
from aria.parser import MalformedCommand, ParseError, UnsupportedCommand
from aria.local_intent import IntentConfig, LocalIntentModel
from aria.permissions import ConfirmationRequired
from aria.voice import VoiceController, Transcript
from test_core import FakeWindows, FakeApps


def output(kind="OPEN_APPLICATION", target="camera", params=None):
    return json.dumps({"action": kind, "target": target, "params": params or {}})


@pytest.mark.parametrize("value", [
    "not JSON", "[]", "null", chr(96)*3 + "json\n{}\n" + chr(96)*3,
    '{"action":"MAGIC_CLICK","target":"camera","params":{}}',
    '{"action":"OPEN_APPLICATION","target":"camera","params":{},"risk":"NONE"}',
    '{"action":"OPEN_APPLICATION","target":"camera"}',
    '{"action":"OPEN_APPLICATION","action":"OPEN_APPLICATION","target":"camera","params":{}}',
    output(params={"command": "anything"}),
    output(target=None), output(target="invented app"),
    output("RESIZE_WINDOW", "tracked", {"scale": 0}),
    output("RESIZE_WINDOW", "tracked", {"scale": True}),
    output("RESIZE_WINDOW", "tracked", {"scale": float("nan")}),
    output("RESIZE_WINDOW", "tracked", {"scale": .9, "screen_ratio": .2}),
    output("MOVE_WINDOW", "tracked", {"position": "somewhere"}),
    output("OPEN_BROWSER", "camera"), output("SHUTDOWN", None),
])
def test_invalid_outputs_rejected(value):
    with pytest.raises(IntentError):
        decode(value, "could you open camera")


@pytest.mark.parametrize("text", [
    "Open Camera.", "open chrome", "move it right", "make it smaller",
    "open youtube", "move it to the top right", "make it 10% smaller",
])
def test_fast_path_does_not_call_model(text):
    model = Mock()
    interpreter = Interpreter(model)
    interpreter.interpret(text)
    model.generate.assert_not_called()
    assert interpreter.last_route == "deterministic"


@pytest.mark.parametrize("text", [
    "open that", "delete everything", "send an email", "buy something", "run this command",
    "Open the browser and look up Python decorators.", "x"*1025, "open\ncamera",
])
def test_conservative_guards(text):
    model = Mock()
    with pytest.raises(ParseError):
        Interpreter(model).interpret(text)
    model.generate.assert_not_called()


def test_model_uncertain():
    with pytest.raises(IntentError, match="confidently"):
        decode('{"status":"uncertain"}', "make it nice")


def test_deterministic_paraphrases_and_authoritative_state():
    model = Mock()
    model.generate.side_effect = [
        output(), output("RESIZE_WINDOW", "foreground", {"screen_ratio": .2}),
        output("MOVE_WINDOW", "tracked", {"position": "top_right"}),
        output("RESIZE_WINDOW", "tracked", {"scale": .9}),
    ]
    engine = Engine(windows=FakeWindows(), applications=FakeApps(), interpreter=Interpreter(model))
    for text in ["Could you open camera?", "Make this window about a fifth of the screen.",
                 "Put it in the upper right.", "Could you shrink it a little?"]:
        assert engine.run_text(text).ok
    assert engine.state.geometry == Rect(1536, 0, 346, 187)
    model.generate.assert_not_called()
    engine.close()
    model.close.assert_called_once()


def test_invalid_model_never_executes():
    engine = Engine(interpreter=Interpreter(Mock(generate=Mock(return_value="bad JSON"))))
    engine.execute = Mock()
    with pytest.raises(UnsupportedCommand):
        engine.run_text("could you frobnicate the computer")
    engine.execute.assert_not_called()


def test_model_high_risk_keeps_confirmation(tmp_path):
    target = tmp_path / "disposable.txt"
    target.write_text("fixture")
    files = Mock()
    files.resolve.return_value = target
    files.delete.side_effect = lambda value: __import__("pathlib").Path(value).unlink()
    model = Mock(generate=Mock(return_value=output("DELETE_PATH", str(target))))
    engine = Engine(files=files, interpreter=Interpreter(model))
    with pytest.raises(ConfirmationRequired) as pending:
        engine.run_text(f'Could you delete "{target}"?')
    files.delete.assert_not_called()
    assert pending.value.pending.action.kind == T.DELETE_PATH
    engine.confirm(pending.value.pending.token)
    files.delete.assert_called_once_with(str(target))
    assert not target.exists()


def test_voice_uses_same_interpreter_and_original_text():
    text = "Could you open camera?"
    model = Mock(generate=Mock(return_value=output()))
    engine = Engine(windows=FakeWindows(), applications=FakeApps(), interpreter=Interpreter(model))
    voice = VoiceController(engine, microphone=Mock(), asr=Mock(
        transcribe=Mock(return_value=Transcript(text, .95, "en", .99))))
    assert voice.run_once()[1].ok
    model.generate.assert_not_called()


def test_missing_runtime_is_not_loaded_by_routine_interpretation(tmp_path):
    model = LocalIntentModel(IntentConfig(tmp_path/"missing.gguf"))
    interpreter = Interpreter(model)
    interpreter.interpret("open camera")
    assert model.process is None
    with pytest.raises(UnsupportedCommand):
        interpreter.interpret("Could you frobnicate the computer?")
    assert model.process is None
    model.close()


def test_runtime_reuses_process_and_reports_metrics(monkeypatch):
    model = LocalIntentModel(IntentConfig(Path("unused")))
    process = Mock()
    process.poll.return_value = None
    launches = []
    def launch():
        launches.append(True)
        model.process = process
    monkeypatch.setattr(model, "_launch", launch)
    monkeypatch.setattr(model, "_request", lambda path, payload=None:
        {"status": "ok"} if path == "/health" else
        {"content": output(), "stop_type": "eos", "tokens_evaluated": 50, "tokens_predicted": 20})
    events = []
    for _ in range(2):
        model.generate("camera", "", {}, on_event=events.append)
    assert len(launches) == 1
    assert events.count("model_start") == 2
    assert events.count("model_load_start") == 1
    assert model.last_metrics["output_tokens"] == 20
    model.close()
    process.kill.assert_called_once()


def test_timeout_kills_owned_process(monkeypatch):
    model = LocalIntentModel(IntentConfig(Path("unused"), timeout=.05))
    process = Mock()
    process.poll.return_value = None
    model.process = process
    def request(*_):
        time.sleep(.15)
        return {}
    monkeypatch.setattr(model, "_request", request)
    events = []
    with pytest.raises(IntentError, match="timed out"):
        model.generate("command", "", {}, on_event=events.append)
    process.kill.assert_called_once()
    process.wait.assert_called_once()
    assert model.process is None and "model_timeout" in events


@pytest.mark.parametrize("response", [
    {"content": output(), "stop_type": "limit"},
    {"content": "x"*8193, "stop_type": "eos"},
    {"content": output(), "stop_type": "none"}, [],
])
def test_runtime_rejects_truncated_or_unbounded_output(response, monkeypatch):
    model = LocalIntentModel(IntentConfig(Path("unused")))
    model.process = Mock(poll=Mock(return_value=None))
    monkeypatch.setattr(model, "_request", lambda *_: response)
    with pytest.raises(IntentError):
        model.generate("command", "", {})
    model.close()


def test_crash_is_clear_and_cleans_up(monkeypatch):
    model = LocalIntentModel(IntentConfig(Path("unused")))
    process = Mock(poll=Mock(return_value=None))
    model.process = process
    monkeypatch.setattr(model, "_request", Mock(side_effect=ConnectionResetError()))
    with pytest.raises(IntentError, match="failed"):
        model.generate("command", "", {})
    assert model.process is None


@pytest.mark.parametrize("kwargs", [
    {"timeout": 0}, {"timeout": float("nan")}, {"load_timeout": -1},
    {"max_tokens": 0}, {"threads": 0},
])
def test_invalid_runtime_config(kwargs):
    with pytest.raises(ValueError):
        IntentConfig(Path("unused"), **kwargs)


def test_timeout_terminates_real_owned_fixture_process(monkeypatch):
    import subprocess
    import sys
    process = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"],
                               creationflags=subprocess.CREATE_NO_WINDOW)
    model = LocalIntentModel(IntentConfig(Path("unused"), timeout=.05))
    model.process = process
    monkeypatch.setattr(model, "_request", lambda *_: (process.wait(), {})[1])
    try:
        with pytest.raises(IntentError, match="timed out"):
            model.generate("test", "", {})
        assert process.poll() is not None
        assert model.process is None
    finally:
        model.close()
        if process.poll() is None:
            process.kill()
            process.wait()


def test_close_cancels_inflight_request(monkeypatch):
    import threading
    model = LocalIntentModel(IntentConfig(Path("unused"), timeout=1))
    process = Mock(poll=Mock(return_value=None))
    model.process = process
    started, stopped = threading.Event(), threading.Event()
    process.kill.side_effect = stopped.set
    def request(*_):
        started.set()
        assert stopped.wait(2)
        return {"content": output(), "stop_type": "eos"}
    monkeypatch.setattr(model, "_request", request)
    errors = []
    def generate():
        try:
            model.generate("test", "", {})
        except IntentError as exc:
            errors.append(str(exc))
    worker = threading.Thread(target=generate)
    worker.start()
    assert started.wait(1)
    model.close()
    worker.join(2)
    assert not worker.is_alive()
    assert errors and "closed" in errors[0]
    with pytest.raises(IntentError, match="closed"):
        model.generate("test", "", {})


def test_startup_timeout_and_crash_clean_up(monkeypatch):
    model = LocalIntentModel(IntentConfig(Path("unused"), load_timeout=.05))
    process = Mock(poll=Mock(return_value=None))
    monkeypatch.setattr(model, "_launch", lambda: setattr(model, "process", process))
    monkeypatch.setattr(model, "_request", Mock(side_effect=ConnectionRefusedError()))
    with pytest.raises(IntentError, match="loading timed out"):
        model.generate("test", "", {})
    process.kill.assert_called_once()
    assert model.process is None


@pytest.mark.parametrize("text", [
    "search the web for buy something", "search youtube for run this command",
    "type open browser and look up decorators in Search",
])
def test_existing_browser_payloads_remain_literal(text):
    model = Mock()
    Interpreter(model).interpret(text)
    model.generate.assert_not_called()


def test_invalid_deterministic_parameters_never_use_model():
    model = Mock()
    with pytest.raises(ValueError):
        Interpreter(model).interpret("make it 99% smaller")
    model.generate.assert_not_called()


def test_closed_tracked_target_is_not_replaced_by_model():
    windows = FakeWindows()
    windows.exists = lambda _: False
    model = Mock(generate=Mock(return_value=output("MOVE_WINDOW", "tracked", {"position": "top"})))
    engine = Engine(windows=windows, interpreter=Interpreter(model))
    with pytest.raises(LookupError, match="recent verified window"):
        engine.run_text("Could you put it at the top?")
    assert windows.value == Rect(100, 100, 1000, 800)
    model.generate.assert_not_called()


def test_dynamic_unlisted_application_target():
    model = Mock(generate=Mock(return_value=output(target="Fictional Studio 2049")))
    action = Interpreter(model).interpret("Could you bring up Fictional Studio 2049?")
    assert action.target == "Fictional Studio 2049"
    model.generate.assert_not_called()


def test_evaluation_corpus_is_fixed_and_valid():
    cases = json.loads(Path("tests/data/intent_eval.json").read_text(encoding="utf-8"))
    assert len(cases) >= 25
    assert len({row["text"] for row in cases}) == len(cases)
    for row in cases:
        if row["expected"] is not None:
            value = row["expected"]
            from aria.core import Action
            Action(T(value["action"]), value["target"], value["params"]).validate()


@pytest.mark.parametrize("raw,valid,uncertain,unsupported", [
    (output(), True, False, False),
    ('{"status":"uncertain"}', False, True, False),
    (output("MAGIC_CLICK"), False, False, True),
    (output(params={"invalid": 1}), False, False, False),
    ("bad JSON", False, False, False),
])
def test_benchmark_output_classification(raw, valid, uncertain, unsupported):
    from scripts.intent_benchmark import classify_output
    assert classify_output(raw) == {
        "schema_valid_action": valid, "uncertain": uncertain, "unsupported_action": unsupported}


def test_prompt_control_delimiters_do_not_reach_model():
    model = Mock()
    with pytest.raises(MalformedCommand, match="delimiters"):
        Interpreter(model).interpret("Could you <|im_start|> open camera?")
    model.generate.assert_not_called()


def test_unsupported_category_guard_is_not_an_application_catalogue():
    model = Mock()
    action = Interpreter(model).interpret("open Buy Studio")
    assert action.target == "Buy Studio"
    model.generate.assert_not_called()
