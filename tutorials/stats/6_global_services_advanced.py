# %% [markdown]
"""
# 6. Global Services Advanced

The following example demonstrates how to collect statistics
from several global services.
"""


# %%
import os
import asyncio

from dff.script import Context
from dff.pipeline import Pipeline, ACTOR, ExtraHandlerRuntimeInfo, GlobalExtraHandlerType
from dff.stats import StatsStorage, ExtractorPool, StatsRecord, default_extractor_pool
from dff.utils.testing.toy_script import TOY_SCRIPT
from dff.utils.testing.common import is_interactive_mode


# %% [markdown]
"""
Like any global handler, handlers for statistics collection can be wired
to run at any stage of `Pipeline` execution.

In the following examples, we add handlers before and after all the services
in order to measure the exact running time of the pipeline.
"""


# %%
extractor_pool = ExtractorPool()


async def heavy_service(_):
    await asyncio.sleep(0.02)


@extractor_pool.new_extractor
async def get_pipeline_state(ctx: Context, _, info: ExtraHandlerRuntimeInfo):
    data = {"runtime_state": info["component"]["execution_state"]}
    group_stats = StatsRecord.from_context(ctx, info, data)
    return group_stats


# %%
pipeline_dict = {
    "script": TOY_SCRIPT,
    "start_label": ("greeting_flow", "start_node"),
    "fallback_label": ("greeting_flow", "fallback_node"),
    "components": [
        [heavy_service for _ in range(0, 5)],
        ACTOR,
    ],
}
pipeline = Pipeline.from_dict(pipeline_dict)
pipeline.add_global_handler(
    GlobalExtraHandlerType.BEFORE_ALL, default_extractor_pool["extract_timing_before"]
)
pipeline.add_global_handler(
    GlobalExtraHandlerType.AFTER_ALL, default_extractor_pool["extract_timing_after"]
)
pipeline.add_global_handler(GlobalExtraHandlerType.AFTER_ALL, get_pipeline_state)

if __name__ == "__main__":
    from dff.utils.testing.stats_cli import parse_args

    if is_interactive_mode():
        uri = "clickhouse://{0}:{1}@localhost:8123/{2}".format(
            os.getenv("CLICKHOUSE_USER"),
            os.getenv("CLICKHOUSE_PASSWORD"),
            os.getenv("CLICKHOUSE_DB"),
        )
    else:
        args = parse_args()
        uri = args["uri"]
    stats = StatsStorage.from_uri(uri)
    stats.add_extractor_pool(extractor_pool)
    stats.add_extractor_pool(default_extractor_pool)
    pipeline.run()
