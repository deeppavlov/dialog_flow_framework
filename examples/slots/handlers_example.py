import logging

from dff.core.engine import conditions as cnd
from dff.core.engine.core.keywords import (
    RESPONSE,
    TRANSITIONS,
    PRE_TRANSITIONS_PROCESSING,
    GLOBAL,
    LOCAL,
)
from dff.core.engine.core import Context, Actor

import dff.script.logic.slots
from dff.script.logic.slots import conditions as slot_cnd
from dff.script.logic.slots import processing as slot_procs

import examples.slots._slots_example_utils as example_utils

logger = logging.getLogger(__name__)


pet = dff.script.logic.slots.GroupSlot(
    name="pet",
    children=[
        dff.script.logic.slots.GroupSlot(
            name="pet_info",
            children=[
                dff.script.logic.slots.RegexpSlot(name="sort", regexp=r"(dog|cat)", match_group_idx=1),
                dff.script.logic.slots.RegexpSlot(name="gender", regexp=r"(she|(?<=[^s])he|^he)", match_group_idx=1),
                dff.script.logic.slots.RegexpSlot(name="behaviour", regexp=r"(good|bad)", match_group_idx=1),
            ],
        )
    ],
)
dff.script.logic.slots.add_slots(pet)

# You can use dff.script.logic.slots handlers to define custom functions.
# These include conditions, responses, and processing routines.
# The following function can yield 4 responses depending on slot values:
# - Is he a good boy or a bad boy?
# - Is she a good girl or a bad girl?
# - Is your cat good or is it bad?
# - Is your dog good or is it bad?
def custom_behaviour_question(ctx: Context, actor: Actor):
    template = "Is {pet/pet_info/gender} a good "
    middle = " or a bad "
    new_template = dff.script.logic.slots.get_filled_template(template, ctx, actor, slots=["pet/pet_info/gender"])
    gender = dff.script.logic.slots.get_values(ctx, actor, slots=["pet/pet_info/gender"])[0]
    if gender is None:
        new_template = dff.script.logic.slots.get_filled_template("Is your {pet/pet_info/sort} good or is it bad?", ctx, actor)
    elif gender == "he":
        new_template = new_template + "boy" + middle + "boy?"
    else:
        new_template = new_template + "girl" + middle + "girl?"
    return new_template


def custom_esteem(ctx: Context, actor: Actor):
    value = dff.script.logic.slots.get_values(ctx, actor, slots=["pet/pet_info/behaviour"])[0]
    if value == "bad":
        return "Sorry to hear that."
    else:
        return "Great to hear that!"


script = {
    GLOBAL: {TRANSITIONS: {("pet_flow", "ask"): cnd.regexp(r"^[sS]tart")}},
    "pet_flow": {
        LOCAL: {
            PRE_TRANSITIONS_PROCESSING: {"get_slot": slot_procs.extract(["pet/pet_info/sort"])},
            TRANSITIONS: {
                ("gender_flow", "ask", 1.2): slot_cnd.is_set_all(["pet/pet_info/sort"]),
                ("pet_flow", "repeat_question", 0.8): cnd.true(),
            },
        },
        "ask": {
            RESPONSE: "I heard that you have a pet. Is it a cat, or a dog?",
        },
        "repeat_question": {RESPONSE: "Seriously, is it a cat, or a dog?"},
    },
    "gender_flow": {
        LOCAL: {
            PRE_TRANSITIONS_PROCESSING: {"get_slot": slot_procs.extract(["pet/pet_info/gender"])},
            TRANSITIONS: {
                ("behaviour_flow", "ask", 1.2): slot_cnd.is_set_all(["pet/pet_info/gender"]),
                ("gender_flow", "repeat_question", 0.8): cnd.true(),
            },
        },
        "ask": {
            RESPONSE: "Great! Is it a he, or a she?",
        },
        "repeat_question": {RESPONSE: "I mean, is it a he, or a she? Name whatever is closer."},
    },
    "behaviour_flow": {
        LOCAL: {
            PRE_TRANSITIONS_PROCESSING: {"get_slot": slot_procs.extract(["pet/pet_info/behaviour"])},
            TRANSITIONS: {
                ("root", "esteem", 1.2): slot_cnd.is_set_all(["pet/pet_info/behaviour"]),
                ("behaviour_flow", "repeat_question", 0.8): cnd.true(),
            },
        },
        "ask": {RESPONSE: custom_behaviour_question},
        "repeat_question": {RESPONSE: custom_behaviour_question},
    },
    "root": {
        "start": {RESPONSE: "", TRANSITIONS: {("pet_flow", "ask"): cnd.true()}},
        "fallback": {
            RESPONSE: "It's been a nice talk! See you.",
            TRANSITIONS: {("pet_flow", "ask"): cnd.true()},
            PRE_TRANSITIONS_PROCESSING: {"forget": slot_procs.unset(["pet"])},
        },
        "esteem": {
            RESPONSE: custom_esteem,
            TRANSITIONS: {("root", "fallback"): cnd.true()},
        },
    },
}

testing_dialog = [
    ("hi", "I heard that you have a pet. Is it a cat, or a dog?"),
    ("it is a dog", "Great! Is it a he, or a she?"),
    ("he", "Is he a good boy or a bad boy?"),
    ("it's bad", "Sorry to hear that."),
    ("ok", "It's been a nice talk! See you."),
    ("ok", "I heard that you have a pet. Is it a cat, or a dog?"),
    ("a CAT", "Seriously, is it a cat, or a dog?"),
    ("it's a cat", "Great! Is it a he, or a she?"),
    ("she", "Is she a good girl or a bad girl?"),
    ("she is good", "Great to hear that!"),
]

actor = Actor(
    script=script,
    start_label=("root", "start"),
    fallback_label=("root", "fallback"),
)
dff.script.logic.slots.register_storage(actor, storage=dict())

if __name__ == "__main__":
    logging.basicConfig(
        format="%(asctime)s-%(name)15s:%(lineno)3s:%(funcName)20s():%(levelname)s - %(message)s",
        level=logging.INFO,
    )
    example_utils.run_interactive_mode(actor)
