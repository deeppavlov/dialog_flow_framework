from pathlib import Path
from typing import List, Optional, Set, Union, Tuple


def create_notebook_link(source: Path, destination: Path):
    """
    Create a symlink between two files.
    Used to create links to examples under docs/source/examples/ root.

    :param source: Path to source file (in examples/ dir).
    :param destination: Path to link file (in docs/source/examples/ dir).
    """
    destination.unlink(missing_ok=True)
    destination.parent.mkdir(exist_ok=True, parents=True)
    destination.symlink_to(source.resolve(), False)


def generate_nb_gallery(package: str, files: List[Path]) -> str:
    """
    Generate a gallery of examples.

    :param package: Package to join into a gallery (effectively a common example link prefix).
    :param files: List of all example links.
    """
    included = "\n   ".join(file.name for file in files if file.name.startswith(package))
    return f"""
.. nbgallery::
   {included}
"""


def create_index_file(
    included: Union[Tuple[str, str], Tuple[str, List[Tuple[str, str]]]],
    files: List[Path],
    destination: Path
):
    """
    Create a package index file.
    Contains a nbgalleries of files inside the package (and subpackages).

    :param included: A pair of package path and alias with or without list of subpackages.
    :param files: List of all example links.
    :param destination: Path to the index file.
    """
    title = included[1]
    contents = f""":orphan:

.. This is an auto-generated RST index file representing examples directory structure

{title}
{"=" * len(title)}
"""
    if len(included) == 2:
        contents += generate_nb_gallery(included[0], files)
    else:
        for subpackage in included[2]:
            contents += f"\n{subpackage[1]}\n{'-' * len(subpackage[1])}\n"
            contents += generate_nb_gallery(f"{included[0]}.{subpackage[0]}", files)

    destination.parent.mkdir(exist_ok=True, parents=True)
    destination.write_text(contents)


def sort_example_file_tree(files: Set[Path]) -> List[Path]:
    """
    Sort files alphabetically; for the example files (whose names start with number) numerical sort is applied.

    :param files: Files list to sort.
    """
    examples = {file for file in files if file.stem.split("_")[0].isdigit()}
    return sorted(examples, key=lambda file: int(file.stem.split("_")[0])) + sorted(files - examples)


def iterate_examples_dir_generating_links(source: Path, dest: Path, base: str) -> List[Path]:
    """
    Recursively travel through examples directory, creating links for all files under docs/source/examples/ root.
    Created link files have dot-path name matching source file tree structure.

    :param source: Examples root (usually examples/).
    :param dest: Examples destination (usually docs/source/examples/).
    :param base: Dot path to current dir (will be used for link file naming).
    """
    if not source.is_dir():
        raise Exception(f"Entity {source} appeared to be a file during processing!")
    links = list()
    for entity in [obj for obj in sort_example_file_tree(set(source.glob("./*"))) if not obj.name.startswith("__")]:
        base_name = f"{base}.{entity.name}"
        if entity.is_file() and entity.suffix in (".py", ".ipynb"):
            base_path = Path(base_name)
            create_notebook_link(entity, dest / base_path)
            links += [base_path]
        elif entity.is_dir() and not entity.name.startswith("_"):
            links += iterate_examples_dir_generating_links(entity, dest, base_name)
    return links


def generate_example_links_for_notebook_creation(
    include: Optional[List[Union[Tuple[str, str], Tuple[str, List[Tuple[str, str]]]]]] = None,
    exclude: Optional[List[str]] = None,
    source: str = "examples",
    destination: str = "docs/source/examples",
):
    """
    Generate symbolic links to examples files (examples/) in docs directory (docs/source/examples/).
    That is required because Sphinx doesn't allow to include files from parent directories into documentation.
    Also, this function creates index files inside each generated folder.
    That index includes each folder contents, so any folder can be imported with 'folder/index'.

    :param include: Files to copy (supports file templates, like *).
    :param exclude: Files to skip (supports file templates, like *).
    :param source: Examples root, default: 'examples/'.
    :param destination: Destination root, default: 'docs/source/examples/'.
    """
    include = [("examples", "Examples")] if include is None else include
    exclude = list() if exclude is None else exclude
    dest = Path(destination)

    flattened = list()
    for package in include:
        if len(package) == 2:
            flattened += [package[0]]
        else:
            flattened += [f"{package[0]}.{subpackage[0]}" for subpackage in package[2]]

    links = iterate_examples_dir_generating_links(Path(source), dest, source)
    filtered_links = list()
    for link in links:
        link_included = len(list(flat for flat in flattened if link.name.startswith(flat))) > 0
        link_excluded = len(list(pack for pack in exclude if link.name.startswith(pack))) > 0
        if link_included and not link_excluded:
            filtered_links += [link]

    for included in include:
        create_index_file(included, filtered_links, dest / Path(f"index_{included[1].replace(' ', '_').lower()}.rst"))