import asyncio
import sys
import pathlib

from dff.script import RESPONSE, TRANSITIONS
from dff.messengers.common import CLIMessengerInterface, CallbackMessengerInterface
from dff.pipeline import Pipeline
import dff.script.conditions as cnd

SCRIPT = {
    "pingpong_flow": {
        "start_node": {
            RESPONSE: "",
            TRANSITIONS: {"node1": cnd.exact_match("Ping")},
        },
        "node1": {
            RESPONSE: "Pong",
            TRANSITIONS: {"node1": cnd.exact_match("Ping")},
        },
        "fallback_node": {
            RESPONSE: "Ooops",
            TRANSITIONS: {"node1": cnd.exact_match("Ping")},
        },
    }
}

pipeline = Pipeline.from_script(
    SCRIPT,
    start_label=("pingpong_flow", "start_node"),
    fallback_label=("pingpong_flow", "fallback_node"),
)


def test_cli_messenger_interface(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "Ping")
    sys.path.append(str(pathlib.Path(__file__).parent.absolute()))

    pipeline.messenger_interface = CLIMessengerInterface(intro="Hi, it's DFF powered bot, let's chat!")

    def loop() -> bool:
        loop.runs_left -= 1
        return loop.runs_left >= 0

    loop.runs_left = 5

    # Literally what happens in pipeline.run()
    asyncio.run(pipeline.messenger_interface.connect(pipeline._run_pipeline, loop=loop))


def test_callback_messenger_interface(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "Ping")
    sys.path.append(str(pathlib.Path(__file__).parent.absolute()))

    interface = CallbackMessengerInterface()
    pipeline.messenger_interface = interface

    # Literally what happens in pipeline.run()
    asyncio.run(pipeline.messenger_interface.connect(pipeline._run_pipeline))

    for _ in range(0, 5):
        assert interface.on_request("Ping", 0).last_response == "Pong"
