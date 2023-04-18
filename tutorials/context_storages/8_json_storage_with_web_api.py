# %% [markdown]
"""
# 8. JSON storage with web API

This is a tutorial on using JSON with web API.
"""


# %%
import pathlib

from dff.context_storages import context_storage_factory

from dff.pipeline import Pipeline
from dff.utils.testing.common import check_happy_path, is_interactive_mode
from dff.utils.testing.toy_script import TOY_SCRIPT_ARGS, HAPPY_PATH

from flask import Flask, request


# %%
app = Flask(__name__)

pathlib.Path("dbs").mkdir(exist_ok=True)
db = context_storage_factory("json://dbs/file.json")


@app.route("/chat", methods=["GET", "POST"])
def respond():
    user_id = str(request.values.get("id"))
    user_message = str(request.values.get("message"))
    context = pipeline(user_message, user_id)
    return {"response": str(context.last_response)}


# %%
pipeline = Pipeline.from_script(*TOY_SCRIPT_ARGS, context_storage=db)


# %%
if __name__ == "__main__":
    check_happy_path(pipeline, HAPPY_PATH)
    if is_interactive_mode():
        app.run(
            host="0.0.0.0", port=5000, debug=True
        )  # This runs tutorial in interactive mode (via flask, as a web server)
