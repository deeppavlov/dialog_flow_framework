from dff.script import TRANSITIONS
from dff.script import RESPONSE
import dff.script.conditions as cnd
from dff.pipeline import Pipeline

toy_script = {
    'flow_start': {
        'node_start': {
            RESPONSE: response_handler,
            TRANSITIONS: {
                ('flow_start', 'node_start'): cnd.true(),
            },
        },
    },
}

pipeline = Pipeline.from_script(toy_script, start_label=('flow_start', 'node_start'), post_services=[process_response])