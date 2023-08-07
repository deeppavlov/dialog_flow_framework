# %% [markdown]
"""
# 2. Pipeline Integration

In the DFF ecosystem, extractor functions act as regular extra handlers (see `pipeline` module
[documentation](https://deeppavlov.github.io/dialog_flow_framework/tutorials/
tutorials.pipeline.7_extra_handlers_basic.html) ).
Hence, you can decorate any part of your pipeline, including services,
service groups and the pipeline as a whole, to obtain the statistics
specific for that component. Some examples of this functionality
are showcased in this tutorial.
"""

# %%
import asyncio

from dff.script import Context
from dff.pipeline import (
    Pipeline,
    ACTOR,
    Service,
    ExtraHandlerRuntimeInfo,
    ServiceGroup,
    GlobalExtraHandlerType,
)
from dff.utils.testing.toy_script import TOY_SCRIPT, HAPPY_PATH
from dff.stats import OtelInstrumentor, set_logger_destination, set_tracer_destination
from dff.stats import OTLPLogExporter, OTLPSpanExporter
from dff.stats import default_extractors
from dff.utils.testing import is_interactive_mode, check_happy_path

# %%
set_logger_destination(OTLPLogExporter("grpc://localhost:4317", insecure=True))
set_tracer_destination(OTLPSpanExporter("grpc://localhost:4317", insecure=True))
dff_instrumentor = OtelInstrumentor()
dff_instrumentor.instrument()


# example extractor function
@dff_instrumentor
async def get_service_state(ctx: Context, _, info: ExtraHandlerRuntimeInfo):
    # extract execution state of service from info
    data = {
        "execution_state": info.component.execution_state,
    }
    # return a record to save into connected database
    return data


# %%
# example service
async def heavy_service(ctx: Context):
    _ = ctx  # get something from ctx if needed
    await asyncio.sleep(0.02)


# %% [markdown]
"""

The many ways in which you can use extractor functions are shown in the following
pipeline definition. The functions are used to obtain statistics from respective components:

* A service group of two `heavy_service` instances.
* An `Actor` service.
* The pipeline as a whole.

As is the case with the regular extra handler functions, you can wire the extractors
to run either before or after the target service. As a result, you can compare
the pre-service and post-service states of the context to measure the performance
of various components, etc.

"""
# %%
pipeline = Pipeline.from_dict(
    {
        "script": TOY_SCRIPT,
        "start_label": ("greeting_flow", "start_node"),
        "fallback_label": ("greeting_flow", "fallback_node"),
        "components": [
            ServiceGroup(
                before_handler=[default_extractors.get_timing_before],
                after_handler=[
                    get_service_state,
                    default_extractors.get_timing_after,
                ],
                components=[{"handler": heavy_service}, {"handler": heavy_service}],
            ),
            Service(
                handler=ACTOR,
                before_handler=[default_extractors.get_timing_before],
                after_handler=[
                    get_service_state,
                    default_extractors.get_timing_after,
                    default_extractors.get_current_label,
                ],
            ),
        ],
    }
)
pipeline.add_global_handler(GlobalExtraHandlerType.BEFORE_ALL, default_extractors.get_timing_before)
pipeline.add_global_handler(GlobalExtraHandlerType.AFTER_ALL, default_extractors.get_timing_after)
pipeline.add_global_handler(GlobalExtraHandlerType.AFTER_ALL, get_service_state)

if __name__ == "__main__":
    check_happy_path(pipeline, HAPPY_PATH)
    if is_interactive_mode():
        pipeline.run()
