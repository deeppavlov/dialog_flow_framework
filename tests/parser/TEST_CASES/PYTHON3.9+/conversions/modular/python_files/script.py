from flows.start import flow
from dff.script import Actor


act = Actor(script={"start_flow": flow}, start_label=("start_flow", "start_node"))
