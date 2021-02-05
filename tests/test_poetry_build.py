import sys
import os
import subprocess
import re
import pathlib

import pytest

here = os.path.dirname(os.path.realpath(__file__))
repo_dir = pathlib.Path(f"{here}/../").resolve()
dist_dir = pathlib.Path(f"{repo_dir}/dist").resolve()

build_file_re = re.compile(r"^\s*- Built (.*)\s*$", flags=re.IGNORECASE | re.MULTILINE)


@pytest.mark.parametrize("pkgformat", ["sdist", "wheel"])
def test_package_install(tmp_path, pkgformat):
    build_output = subprocess.check_output(
        ["poetry", "build", "-n", "-f", pkgformat],
        cwd=repo_dir,
        universal_newlines=True,
    )
    assert build_output
    m = build_file_re.search(build_output)
    assert m
    bname = m.group(1)
    venv_path = tmp_path / "venv"
    subprocess.check_call(["virtualenv", "-p", sys.executable, venv_path])
    subprocess.check_call([venv_path / "bin/pip", "install", dist_dir / bname])
    subprocess.check_call([venv_path / "bin/jjm", "--help"])
