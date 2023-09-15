# %% [markdown]
"""
# 3. Sample data provider

This script demonstrates various instrumentation capabilities.
It also provides data for the dashboard emulating simultaneous queries
to the service by multiple users.

"""

# %pip install dff[stats]

# %%
import random
import asyncio
from tqdm import tqdm
from dff.script import Context, Message
from dff.pipeline import Pipeline, Service, ACTOR, ExtraHandlerRuntimeInfo
from dff.stats import (
    default_extractors,
    OtelInstrumentor,
)
from dff.utils.testing import is_interactive_mode
from dff.utils.testing.toy_script import MULTIFLOW_SCRIPT, MULTIFLOW_REQUEST_OPTIONS

# %%
# instrumentation code
dff_instrumentor = OtelInstrumentor.from_url("grpc://localhost:4317", insecure=True)
dff_instrumentor.instrument()


def slot_processor_1(ctx: Context):
    ctx.misc["slots"] = {"rating": random.randint(1, 10)}


def slot_processor_2(ctx: Context):
    ctx.misc["slots"] = {"current_topic": random.choice(["films", "games", "books", "smalltalk"])}


@dff_instrumentor
async def get_slots(ctx: Context, _, info: ExtraHandlerRuntimeInfo):
    return ctx.misc["slots"]


def confidence_processor(ctx: Context):
    ctx.framework_states["response_confidence"] = random.random()


@dff_instrumentor
async def get_confidence(ctx: Context, _, info: ExtraHandlerRuntimeInfo):
    data = {"response_confidence": ctx.framework_states["response_confidence"]}
    return data


# %%
pipeline = Pipeline.from_dict(
    {
        "script": MULTIFLOW_SCRIPT,
        "start_label": ("root", "start"),
        "fallback_label": ("root", "fallback"),
        "components": [
            Service(slot_processor_1, after_handler=[get_slots]),
            Service(slot_processor_2, after_handler=[get_slots]),
            Service(confidence_processor, after_handler=[get_confidence]),
            Service(
                handler=ACTOR,
                before_handler=[default_extractors.get_timing_before],
                after_handler=[
                    default_extractors.get_timing_after,
                    default_extractors.get_current_label,
                    default_extractors.get_last_request,
                    default_extractors.get_last_response,
                ],
            ),
        ],
    }
)


# %%
async def worker(queue: asyncio.Queue):
    """
    Worker function for dispatching one client message.

    :param queue: Queue for sharing context variables.
    """
    ctx: Context = await queue.get()
    label = ctx.last_label if ctx.last_label else pipeline.actor.fallback_label
    flow, node = label[:2]
    if [flow, node] == ["root", "fallback"]:
        rand_interval = float(random.randint(0, 1)) + random.random()
        await asyncio.sleep(rand_interval)
        ctx = Context()
        flow, node = ["root", "start"]
    answers = list(MULTIFLOW_REQUEST_OPTIONS.get(flow, {}).get(node, []))
    in_text = random.choice(answers) if answers else "go to fallback"
    in_message = Message(text=in_text)
    rand_interval = float(random.randint(0, 1)) + random.random()
    await asyncio.sleep(rand_interval)
    ctx = await pipeline._run_pipeline(in_message, ctx.id)
    rand_interval = float(random.randint(0, 1)) + random.random()
    await asyncio.sleep(rand_interval)
    await queue.put(ctx)


# %%
# main loop
async def main(n_iterations: int = 100, n_workers: int = 4):
    """
    Main loop that runs one or more worker coroutines in parallel.

    :param n_iterations: Total number of coroutine runs.
    :param n_workers: Number of parallelized coroutine runs.
    """
    ctxs = asyncio.Queue()
    parallel_iterations = n_iterations // n_workers
    for _ in range(n_workers):
        await ctxs.put(Context())
    for _ in tqdm(range(parallel_iterations)):
        await asyncio.gather(*(worker(ctxs) for _ in range(n_workers)))


if __name__ == "__main__":
    if is_interactive_mode():
        asyncio.run(main())
