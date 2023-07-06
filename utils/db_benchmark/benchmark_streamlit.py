"""
Benchmark Streamlit
-------------------
This module provides a streamlit interface to view benchmark results.
The interface has 4 tabs:

- "Benchmark sets" -- Here you can add or remove benchmark set files (generated by `save_results_to_file` function).
- "View" -- Here you can view various stats for each benchmark in the set (as well as add benchmarks to compare tab).
- "Compare" -- Here you can compare benchmarks added via "View" tab.
- "Mass compare" -- This tab lets you compare all benchmarks in a particular set.

Run this file with `streamlit run {path/to/this/file}`.

When run, this module will search for a file named "benchmark_results_files.json" in the directory
where the command above was executed.
If the file does not exist there, it will be created.
The file is used to store paths to benchmark result files.

Benchmark result files added via this module are not changed (only read).
"""
import json
from pathlib import Path

import pandas as pd
from pympler import asizeof
from humanize import naturalsize
import altair as alt
import streamlit as st


st.set_page_config(
    page_title="DB benchmark",
    layout="wide",
    initial_sidebar_state="expanded",
)

BENCHMARK_RESULTS_FILES = Path("benchmark_results_files.json")
# This file stores links to benchmark set files generated by `save_results_to_file`.


if not BENCHMARK_RESULTS_FILES.exists():
    with open(BENCHMARK_RESULTS_FILES, "w", encoding="utf-8") as fd:
        json.dump([], fd)

if "benchmark_files" not in st.session_state:
    with open(BENCHMARK_RESULTS_FILES, "r", encoding="utf-8") as fd:
        st.session_state["benchmark_files"] = json.load(fd)

if "benchmarks" not in st.session_state:
    st.session_state["benchmarks"] = {}

    for file in st.session_state["benchmark_files"]:
        with open(file, "r", encoding="utf-8") as fd:
            st.session_state["benchmarks"][file] = json.load(fd)

if "compare" not in st.session_state:
    st.session_state["compare"] = []


def add_metrics(container, value_benchmark):
    write, read, update, read_update = container.columns(4)
    column_names = ("write", "read", "update", "read+update")

    if not value_benchmark["success"]:
        values = {key: "-" for key in column_names}
    else:
        values = {key: value_benchmark["average_results"][f"pretty_{key}"] for key in column_names}

    columns = {
        "write": write,
        "read": read,
        "update": update,
        "read+update": read_update,
    }

    for column_name, column in columns.items():
        column.metric(
            column_name.title(),
            values[column_name],
        )


st.sidebar.text(f"Benchmarks take {naturalsize(asizeof.asizeof(st.session_state['benchmarks']))} RAM")

add_tab, view_tab, compare_tab, mass_compare_tab = st.tabs(["Benchmark sets", "View", "Compare", "Mass compare"])


###############################################################################
# Benchmark file manipulation tab
# Allows adding and deleting benchmark files
###############################################################################

with add_tab:
    benchmark_list = []

    for file, benchmark_set in st.session_state["benchmarks"].items():
        benchmark_list.append(
            {
                "file": file,
                "name": benchmark_set["name"],
                "description": benchmark_set["description"],
                "uuid": benchmark_set["uuid"],
                "delete": False,
            }
        )

    df = pd.DataFrame(data=benchmark_list)
    edited_df = st.data_editor(df, disabled=("file", "name", "description", "uuid"))

    delist_container = st.container()
    delist_container.divider()

    def delist_benchmarks():
        delisted_sets = [
            f"{name} ({uuid})" for name, uuid in edited_df.loc[edited_df["delete"]][["name", "uuid"]].values
        ]

        st.session_state["compare"] = [
            item for item in st.session_state["compare"] if item["benchmark_set"] not in delisted_sets
        ]

        files_to_delist = edited_df.loc[edited_df["delete"]]["file"]
        st.session_state["benchmark_files"] = list(set(st.session_state["benchmark_files"]) - set(files_to_delist))
        for file in files_to_delist:
            del st.session_state["benchmarks"][file]
            delist_container.text(f"Delisted {file}")

        with open(BENCHMARK_RESULTS_FILES, "w", encoding="utf-8") as fd:
            json.dump(list(st.session_state["benchmark_files"]), fd)

    delist_container.button(label="Delist selected benchmark sets", on_click=delist_benchmarks)

    add_container = st.container()
    add_container.divider()

    add_container.text_input(label="Benchmark set file", key="add_benchmark_file")

    def add_benchmark():
        benchmark_file = st.session_state["add_benchmark_file"]
        if benchmark_file == "":
            return

        if benchmark_file in st.session_state["benchmark_files"]:
            add_container.warning("Benchmark file already added")
            return

        if not Path(benchmark_file).exists():
            add_container.warning("File does not exists")
            return

        with open(benchmark_file, "r", encoding="utf-8") as fd:
            file_contents = json.load(fd)

        for benchmark in st.session_state["benchmarks"].values():
            if file_contents["uuid"] == benchmark["uuid"]:
                add_container.warning("Benchmark with the same uuid already exists")
                return

        st.session_state["benchmark_files"].append(benchmark_file)
        with open(BENCHMARK_RESULTS_FILES, "w", encoding="utf-8") as fd:
            json.dump(list(st.session_state["benchmark_files"]), fd)
        st.session_state["benchmarks"][benchmark_file] = file_contents

        add_container.text(f"Added {benchmark_file} set")

    add_container.button("Add benchmark set from file", on_click=add_benchmark)

###############################################################################
# View tab
# Allows viewing existing benchmarks
###############################################################################

with view_tab:
    set_choice, benchmark_choice, compare = st.columns([3, 3, 1])

    sets = {
        f"{benchmark['name']} ({benchmark['uuid']})": benchmark for benchmark in st.session_state["benchmarks"].values()
    }
    benchmark_set = set_choice.selectbox("Benchmark set", sets.keys())

    if benchmark_set is None:
        set_choice.warning("No benchmark sets available")
        st.stop()

    selected_set = sets[benchmark_set]

    set_choice.text("Set description:")
    set_choice.markdown(selected_set["description"])

    benchmarks = {f"{benchmark['name']} ({benchmark['uuid']})": benchmark for benchmark in selected_set["benchmarks"]}

    benchmark = benchmark_choice.selectbox("Benchmark", benchmarks.keys())

    if benchmark is None:
        benchmark_choice.warning("No benchmarks in the set")
        st.stop()

    selected_benchmark = benchmarks[benchmark]

    benchmark_choice.text("Benchmark description:")
    benchmark_choice.markdown(selected_benchmark["description"])

    with st.expander("Benchmark stats"):
        reproducible_stats = {
            stat: selected_benchmark[stat]
            for stat in (
                "db_factory",
                "benchmark_config",
            )
        }

        size_stats = {stat: naturalsize(value, gnu=True) for stat, value in selected_benchmark["sizes"].items()}

        st.json(reproducible_stats)
        st.json(size_stats)

    if not selected_benchmark["success"]:
        st.warning(selected_benchmark["result"])
    else:
        add_metrics(st.container(), selected_benchmark)

        compare_item = {
            "benchmark_set": benchmark_set,
            "benchmark": benchmark,
            "write": selected_benchmark["average_results"]["pretty_write"],
            "read": selected_benchmark["average_results"]["pretty_read"],
            "update": selected_benchmark["average_results"]["pretty_update"],
            "read+update": selected_benchmark["average_results"]["pretty_read+update"],
        }

        def add_results_to_compare_tab():
            if compare_item not in st.session_state["compare"]:
                st.session_state["compare"].append(compare_item)
            else:
                st.session_state["compare"].remove(compare_item)

        compare.button(
            "Add to Compare" if compare_item not in st.session_state["compare"] else "Remove from Compare",
            on_click=add_results_to_compare_tab,
        )

        select_graph, graph = st.columns([1, 3])

        average_results = selected_benchmark["average_results"]

        graphs = {
            "Write": selected_benchmark["result"]["write_times"],
            "Read (grouped by contex_num)": average_results["read_times_grouped_by_context_num"],
            "Read (grouped by dialog_len)": average_results["read_times_grouped_by_dialog_len"],
            "Update (grouped by contex_num)": average_results["update_times_grouped_by_context_num"],
            "Update (grouped by dialog_len)": average_results["update_times_grouped_by_dialog_len"],
        }

        selected_graph = select_graph.selectbox("Select graph to display", graphs.keys())

        graph_data = graphs[selected_graph]

        if isinstance(graph_data, dict):
            data = pd.DataFrame({"dialog_len": graph_data.keys(), "time": graph_data.values()})
        else:
            data = pd.DataFrame({"context_num": range(len(graph_data)), "time": graph_data})

        chart = (
            alt.Chart(data)
            .mark_circle()
            .encode(
                x=alt.X(
                    "dialog_len:Q" if isinstance(graph_data, dict) else "context_num:Q", scale=alt.Scale(zero=False)
                ),
                y="time:Q",
            )
            .interactive()
        )

        graph.altair_chart(chart, use_container_width=True)


###############################################################################
# Compare tab
# Allows viewing existing benchmarks
###############################################################################

with compare_tab:
    df = pd.DataFrame(st.session_state["compare"])

    if not df.empty:
        st.dataframe(
            df.style.highlight_min(
                axis=0, subset=["write", "read", "update", "read+update"], props="background-color:green;"
            ).highlight_max(axis=0, subset=["write", "read", "update", "read+update"], props="background-color:red;")
        )

###############################################################################
# Mass compare tab
# Allows comparing all benchmarks inside a single set
###############################################################################

with mass_compare_tab:
    sets = {
        f"{benchmark_set['name']} ({benchmark_set['uuid']})": benchmark_set
        for benchmark_set in st.session_state["benchmarks"].values()
    }
    benchmark_set = st.selectbox("Benchmark set", sets.keys(), key="mass_compare_selectbox")

    if benchmark_set is None:
        st.warning("No benchmark sets available")
        st.stop()

    selected_set = sets[benchmark_set]

    compare_items = []

    for selected_benchmark in selected_set["benchmarks"]:
        if selected_benchmark["success"]:
            compare_items.append(
                {
                    "benchmark": f"{selected_benchmark['name']} ({selected_benchmark['uuid']})",
                    "write": selected_benchmark["average_results"]["pretty_write"],
                    "read": selected_benchmark["average_results"]["pretty_read"],
                    "update": selected_benchmark["average_results"]["pretty_update"],
                    "read+update": selected_benchmark["average_results"]["pretty_read+update"],
                }
            )

    df = pd.DataFrame(compare_items)

    if not df.empty:
        st.dataframe(
            df.style.highlight_min(
                axis=0, subset=["write", "read", "update", "read+update"], props="background-color:green;"
            ).highlight_max(axis=0, subset=["write", "read", "update", "read+update"], props="background-color:red;")
        )
