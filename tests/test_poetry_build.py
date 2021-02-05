import sys
import os
import subprocess
import re

import pytest

here = os.path.dirname(os.path.realpath(__file__))
repo_dir = os.path.realpath(f"{here}/../")
dist_dir = os.path.realpath(f"{repo_dir}/dist")

build_file_re = re.compile(r"^\s*- Built (.*)\s*$", flags=re.IGNORECASE | re.MULTILINE)


@pytest.mark.parametrize("pkgformat", ["sdist", "wheel"])
def test_package_install(tmp_path, pkgformat):
    p = subprocess.run(
        ["poetry", "build", "-n", "-f", pkgformat],
        cwd=repo_dir,
        text=True,
        capture_output=True,
        check=True,
    )
    m = build_file_re.search(p.stdout)
    assert m
    bname = m.group(1)
    venv_path = f"{tmp_path}/venv"
    subprocess.check_call(["virtualenv", "-p", sys.executable, venv_path])
    subprocess.check_call([f"{venv_path}/bin/pip", "install", f"{dist_dir}/{bname}"])
    subprocess.check_call([f"{venv_path}/bin/jjm", "--help"])
