# %% [markdown]
"""
# 6. Context serialization

This example shows context serialization.
First of all, let's do all the necessary imports from `dff`.
"""


# %%
import logging

from dff.script import TRANSITIONS, RESPONSE, Context, Actor
import dff.script.conditions as cnd

from dff.pipeline import Pipeline
from dff.utils.testing.common import (
    check_happy_path,
    is_interactive_mode,
    run_interactive_mode,
)


# %% [markdown]
"""
This function returns the user request number.
"""


# %%
def response_handler(ctx: Context, actor: Actor, *args, **kwargs) -> str:
    return f"answer {len(ctx.requests)}"


# %%
# a dialog script
toy_script = {
    "flow_start": {
        "node_start": {
            RESPONSE: response_handler,
            TRANSITIONS: {("flow_start", "node_start"): cnd.true()},
        }
    }
}

# testing
happy_path = (
    ("hi", "answer 1"),
    ("how are you?", "answer 2"),
    ("ok", "answer 3"),
    ("good", "answer 4"),
)

# %% [markdown]
"""
Draft function that performs serialization.
"""


# %%
def process_response(ctx: Context):
    ctx_json = ctx.json()
    if isinstance(ctx_json, str):
        logging.info("context serialized to json str")
    else:
        raise Exception(f"ctx={ctx_json} has to be serialized to json string")

    ctx_dict = ctx.dict()
    if isinstance(ctx_dict, dict):
        logging.info("context serialized to dict")
    else:
        raise Exception(f"ctx={ctx_dict} has to be serialized to dict")

    if not isinstance(ctx, Context):
        raise Exception(f"ctx={ctx} has to have Context type")


# %%
pipeline = Pipeline.from_script(
    toy_script,
    start_label=("flow_start", "node_start"),
    post_services=[process_response],
)

if __name__ == "__main__":
    check_happy_path(pipeline, happy_path)
    if is_interactive_mode():
        run_interactive_mode(pipeline)
