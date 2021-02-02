import os
import pathlib
from dataclasses import dataclass
from functools import partial
from unittest import mock

import pytest
import yaml
from click.testing import CliRunner
from jenkins_job_manager.cli import jjm

HERE = os.path.dirname(os.path.realpath(__file__))


@pytest.fixture(scope="function")
def jjm_runner():
    runner = CliRunner()
    with runner.isolated_filesystem():
        pathlib.Path("./jjm.ini").write_text(
            f"""\
[jenkins]
url = {FakeJenkins._url}
username = {FakeJenkins._username}
password = {FakeJenkins._password}
"""
        )
        yield partial(runner.invoke, jjm, catch_exceptions=False)


class FakeJenkins:
    """a fake class to substitute jenkins api in these tests"""

    _url = "https://127.0.0.1/fakejenkins"
    _username = "fake"
    _password = "alsofake"

    def __init__(self, views=None, jobs=None):
        self.views: list = views or []
        self.jobs: list = jobs or []

    def get_whoami(self):
        return {"id": self._username}

    def get_plugins(self):
        return {}

    def get_views(self):
        return (
            dict(
                name=d["name"],
                url=f"{self._url}/view/{d['name']}",
                _class=d.get("class") or "hudson.View.Something",
            )
            for d in self.views
        )

    def get_view_config(self, name):
        for d in self.views:
            if d["name"] == name:
                return d["xml"]
        return None

    def get_all_jobs(self):
        return (
            dict(
                fullname=d["name"],
                url=f"{self._url}/job/{d['name']}",
                _class=d.get("class") or "jenkins.job.FreeStyleOrSomething",
            )
            for d in self.jobs
        )

    def get_job_config(self, name):
        for d in self.jobs:
            if d["name"] == name:
                return d["xml"]
        return None


@dataclass
class JCase:
    """quick schema for these test cases"""

    name: str
    local: str
    remote: dict
    output_default: str
    output_struct: list


def _test_cases():
    with open(f"{HERE}/test_output_render.yml", "r") as fp:
        test_cases = yaml.safe_load_all(fp)
        for test_case in test_cases:
            if test_case is None:
                continue
            yield JCase(**test_case)


@pytest.mark.parametrize("test_case", _test_cases())
@mock.patch("jenkins_job_manager.core.JenkinsJobManager.jenkins", autospec=True)
def test_jjm_default_plan_output(
    jenkins_api: mock.MagicMock, test_case: JCase, jjm_runner
):
    fake_jenkins = FakeJenkins(**test_case.remote)
    with mock.patch("jenkins_job_manager.core.JenkinsJobManager.jenkins", fake_jenkins):
        # this assumes the "jjm_runner" fixture has us in an isolated filesystem
        pathlib.Path("./job.yml").write_text(test_case.local)

        result = jjm_runner(["plan", "--skip-pager"])
        assert result.output == test_case.output_default
        assert result.exit_code == 0
