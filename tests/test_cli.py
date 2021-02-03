from functools import partial
import logging
import os
import pytest
from unittest import mock
import json

import click.testing
import tomlkit
from jenkins_job_manager import __version__
from jenkins_job_manager.cli import jjm

HERE = os.path.dirname(os.path.realpath(__file__))
PROJECT_DIR = os.path.realpath(HERE + "/../")


def test_version():
    with open(f"{PROJECT_DIR}/pyproject.toml") as fp:
        doc = tomlkit.parse(fp.read())
    print(doc)
    toml_version = doc["tool"]["poetry"]["version"]
    assert __version__ == toml_version


@pytest.fixture
def jjm_runner():
    runner = click.testing.CliRunner()
    return partial(runner.invoke, jjm)


base_args = [
    "-d",
    "-C",
    "/tmp",
    "--url",
    "https://yourjenkinsurl.com/",
]
overrides_url = {"url": "https://yourjenkinsurl.com/"}
overrides_none = {}


@mock.patch("jenkins_job_manager.cli.log", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm_no_args(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
    log,
    jjm_runner,
):
    result = jjm_runner()
    assert result.exit_code == 0
    assert "Usage:" in result.output
    log.setLevel.assert_not_called()
    JenkinsJobManager.assert_not_called()
    JenkinsJobManager.gather.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_not_called()
    handle_validation_errors.assert_not_called()
    handle_plan_report.assert_not_called()


@mock.patch("jenkins_job_manager.cli.log", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm_all_args(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
    log,
    jjm_runner,
):
    result = jjm_runner(base_args)
    assert result.exit_code == 2
    assert "Usage:" in result.output
    log.setLevel.assert_not_called()
    JenkinsJobManager.assert_not_called()
    JenkinsJobManager.gather.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_not_called()
    handle_validation_errors.assert_not_called()
    handle_plan_report.assert_not_called()


@mock.patch("jenkins_job_manager.cli.log", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm_apply_no_args(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
    log,
    jjm_runner,
):
    result = jjm_runner(["apply"])
    assert result.exit_code == 1
    assert "ERROR" not in result.output
    log.setLevel.assert_not_called()
    JenkinsJobManager.assert_called_once_with(overrides_none)
    JenkinsJobManager.gather.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_called_once_with(JenkinsJobManager())
    handle_validation_errors.assert_called_once_with(JenkinsJobManager())
    handle_plan_report.assert_called_once_with(JenkinsJobManager(), use_pager=False)


@mock.patch("jenkins_job_manager.cli.log", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm_apply_all_args(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
    log,
    jjm_runner,
):
    result = jjm_runner(base_args + ["apply"] + ["--target", "bogus"])
    assert result.exit_code == 1
    assert "ERROR" not in result.output
    log.setLevel.assert_called_once_with(logging.DEBUG)
    JenkinsJobManager.assert_called_once_with(overrides_url)
    JenkinsJobManager.gather.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_called_once_with(JenkinsJobManager())
    handle_validation_errors.assert_called_once_with(JenkinsJobManager())
    handle_plan_report.assert_called_once_with(JenkinsJobManager(), use_pager=False)


@mock.patch("jenkins_job_manager.cli.log", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm_check_no_args(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
    log,
    jjm_runner,
):
    result = jjm_runner(["check"])
    assert result.exit_code == 0
    assert "ERROR" not in result.output
    log.setLevel.assert_not_called()
    JenkinsJobManager.assert_called_with(overrides_none)
    JenkinsJobManager.gather.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_not_called()
    handle_validation_errors.assert_called_once_with(JenkinsJobManager())
    handle_plan_report.assert_not_called()


@mock.patch("jenkins_job_manager.cli.log", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm_check_all_args(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
    log,
    jjm_runner,
):
    result = jjm_runner(base_args + ["check", "--load-plugins"])
    assert result.exit_code == 0
    assert "ERROR" not in result.output
    log.setLevel.assert_called_once_with(logging.DEBUG)
    JenkinsJobManager.assert_called_once_with(overrides_url)
    JenkinsJobManager.gather.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_not_called()
    handle_plan_report.assert_not_called()
    handle_validation_errors.assert_called_once_with(JenkinsJobManager())


@mock.patch("jenkins_job_manager.cli.log", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm_import_no_args(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
    log,
    jjm_runner,
):
    result = jjm_runner(["import"])
    assert result.exit_code == 0
    assert "ERROR" not in result.output
    assert "Imported 0 jobs." in result.output
    log.setLevel.assert_not_called()
    JenkinsJobManager.assert_called_once_with(overrides_none)
    JenkinsJobManager.gather.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_called_once_with(JenkinsJobManager())
    handle_validation_errors.assert_not_called()
    handle_plan_report.assert_not_called()


@mock.patch("jenkins_job_manager.cli.log", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm_import_all_args(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
    log,
    jjm_runner,
):
    result = jjm_runner(base_args + ["import"] + ["--target", "bogus"])
    assert result.exit_code == 0
    assert "ERROR" not in result.output
    assert "Imported 0 jobs." in result.output
    log.setLevel.assert_called_once_with(logging.DEBUG)
    JenkinsJobManager.assert_called_once_with(overrides_url)
    JenkinsJobManager.gather.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_called_once_with(JenkinsJobManager())
    handle_validation_errors.assert_not_called()
    handle_plan_report.assert_not_called()


@mock.patch("jenkins_job_manager.cli.log", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm_login_no_args(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
    log,
    jjm_runner,
):
    result = jjm_runner(["login"])
    assert result.exit_code == 1
    assert "ERROR" not in result.output
    assert "Auth already configured for this jenkins" in result.output
    log.setLevel.assert_not_called()
    JenkinsJobManager.assert_called_once_with(overrides_none)
    JenkinsJobManager.gather.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_not_called()
    handle_validation_errors.assert_not_called()
    handle_plan_report.assert_not_called()


@mock.patch("jenkins_job_manager.cli.log", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm_plan_no_args(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
    log,
    jjm_runner,
):
    result = jjm_runner(["plan"])
    assert result.exit_code == 0
    assert "ERROR" not in result.output
    log.setLevel.assert_not_called()
    JenkinsJobManager.assert_called_once_with(overrides_none)
    JenkinsJobManager.gather.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_called_once_with(JenkinsJobManager())
    handle_validation_errors.assert_called_once_with(JenkinsJobManager())
    handle_plan_report.assert_called_once_with(JenkinsJobManager(), use_pager=True, output=None)


@mock.patch("jenkins_job_manager.cli.log", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm_plan_all_args(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
    log,
    jjm_runner,
):
    plan_args = ["--skip-pager", "--target", "bogus"]
    result = jjm_runner(base_args + ["plan"] + plan_args)
    assert result.exit_code == 0
    assert "Usage" not in result.output
    log.setLevel.assert_called_once_with(logging.DEBUG)
    JenkinsJobManager.assert_called_once_with(overrides_url)
    JenkinsJobManager.gather.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_called_once_with(JenkinsJobManager())
    handle_validation_errors.assert_called_once_with(JenkinsJobManager())
    handle_plan_report.assert_called_once_with(JenkinsJobManager(), use_pager=False, output=None)
