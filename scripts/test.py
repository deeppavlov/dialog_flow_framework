import sys
from typing import Optional
import pytest
import dotenv
from python_on_whales import DockerClient

from .codestyle import lint
from .utils import docker_client


def _test(coverage: bool, dependencies: bool):
    test_coverage_threshold = 95

    dotenv.load_dotenv(".env_file")
    args = ["tests/"]

    if dependencies and coverage:
        args = [
            "-m",
            "not no_coverage",
            "--allow-skip=telegram",
            *args,
        ]
    elif dependencies:
        args = [
            "--allow-skip=telegram,docker",
            *args,
        ]
    else:
        args = [
            "--allow-skip=all",
            *args,
        ]

    if "linux" not in sys.platform:
        args = [
            "-m",
            "not docker",
            *args,
        ]
    if coverage:
        args = [
            f"--cov-fail-under={test_coverage_threshold}",
            "--cov-report",
            "html",
            "--cov-report",
            "term",
            "--cov=dff",
            *args,
        ]
    else:
        args = [
            "--tb=long",
            "-vv",
            "--cache-clear",
            *args,
        ]

    pytest.main(args)


def test_no_cov():
    return _test(False, True)


def test_no_deps():
    return _test(False, False)


@docker_client
def test_all(docker: Optional[DockerClient]):
    _test(True, docker is not None)
    lint()


if __name__ == "__main__":
    test_all(None)