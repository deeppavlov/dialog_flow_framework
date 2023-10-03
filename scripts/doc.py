import glob
import os
from pathlib import Path
import shutil
from typing import Optional

import dotenv
import scripts.patch_sphinx  # noqa: F401
import sphinx.ext.apidoc as apidoc
import sphinx.cmd.build as build
from colorama import init, Fore, Style
from python_on_whales import DockerClient

from .utils import docker_client
from .clean import clean_docs


def _build_drawio(docker: DockerClient):
    if len(docker.image.list("rlespinasse/drawio-export")) == 0:
        docker.image.pull("rlespinasse/drawio-export", quiet=True)
    docker.container.run(
        "rlespinasse/drawio-export",
        ["-f", "png", "--remove-page-suffix"],
        remove=True,
        name="drawio-convert",
        volumes=[(f"{os.getcwd()}/docs/source/drawio_src", "/data", "rw")]
    )
    docker.container.run(
        "rlespinasse/drawio-export",
        ["-R", f"{os.geteuid()}:{os.getegid()}", "/data"],
        entrypoint="chown",
        remove=True,
        name="drawio-chown",
        volumes=[(f"{os.getcwd()}/docs/source/drawio_src", "/data", "rw")]
    )

    destination = Path("docs/source/_static/drawio/")
    destination.mkdir(parents=True, exist_ok=True)
    for path in glob.glob("docs/source/drawio_src/**/export"):
        target = destination / Path(path).relative_to("docs/source/drawio_src").parent
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(path, target)


@docker_client
def docs(docker: Optional[DockerClient]) -> int:
    init()
    if docker is not None:
        clean_docs()
        dotenv.load_dotenv(".env_file")
        os.environ["DISABLE_INTERACTIVE_MODE"] = "1"
        _build_drawio(docker)
        result = apidoc.main(["-e", "-E", "-f", "-o", "docs/source/apiref", "dff"])
        result += build.make_main(["-M", "clean", "docs/source", "docs/build"])
        result += build.build_main(["-b", "html", "-W", "--keep-going", "docs/source", "docs/build"])
        return result
    else:
        print(f"{Fore.RED}Docs can be built on Linux platform only!{Style.RESET_ALL}")
        return 1
