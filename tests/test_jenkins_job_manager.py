import logging
import os
from unittest import mock

import click.testing
import tomlkit
from jenkins_job_manager import __version__
from jenkins_job_manager.cli import jjm, log

HERE = os.path.dirname(os.path.realpath(__file__))
PROJECT_DIR = os.path.realpath(HERE + "/../")


def test_version():
    with open(f"{PROJECT_DIR}/pyproject.toml") as fp:
        doc = tomlkit.parse(fp.read())
    print(doc)
    toml_version = doc["tool"]["poetry"]["version"]
    assert __version__ == toml_version


@mock.patch("jenkins_job_manager.cli.handle_plan_report", autospec=True)
@mock.patch("jenkins_job_manager.cli.handle_validation_errors", autospec=True)
@mock.patch("jenkins_job_manager.cli.check_auth", autospec=True)
@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm(
    JenkinsJobManager,
    jjm_check,
    check_auth,
    handle_validation_errors,
    handle_plan_report,
):
    runner = click.testing.CliRunner()
    base_args = ["-d", "-C", "/tmp", "--url", "https://yourjenkinsurl.com/"]
    overrides_url = {"url": "https://yourjenkinsurl.com/"}
    overrides_none = {}

    # no args (no command)
    result = runner.invoke(jjm)
    assert log.getEffectiveLevel() == logging.INFO
    assert result.exit_code == 0
    assert "Usage:" in result.output
    JenkinsJobManager.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_not_called()
    handle_validation_errors.assert_not_called()
    handle_plan_report.assert_not_called()
    JenkinsJobManager.reset_mock()
    check_auth.reset_mock()
    handle_plan_report.reset_mock()
    handle_validation_errors.reset_mock()
    jjm_check.reset_mock()

    # all args (no command)
    result = runner.invoke(jjm, base_args)
    assert log.getEffectiveLevel() == logging.INFO
    assert result.exit_code == 2
    assert "Usage:" in result.output
    JenkinsJobManager.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_not_called()
    handle_validation_errors.assert_not_called()
    handle_plan_report.assert_not_called()
    JenkinsJobManager.reset_mock()
    check_auth.reset_mock()
    handle_plan_report.reset_mock()
    handle_validation_errors.reset_mock()
    jjm_check.reset_mock()

    # apply, no args
    result = runner.invoke(jjm, ["apply"])
    assert log.getEffectiveLevel() == logging.INFO
    assert result.exit_code == 1
    assert "ERROR" not in result.output
    JenkinsJobManager.assert_called_once_with(overrides_none)
    jjm_check.assert_not_called()
    check_auth.assert_called_once_with(JenkinsJobManager())
    handle_validation_errors.assert_called_once_with(JenkinsJobManager())
    handle_plan_report.assert_called_once_with(JenkinsJobManager(), use_pager=False)
    JenkinsJobManager.reset_mock()
    check_auth.reset_mock()
    handle_plan_report.reset_mock()
    handle_validation_errors.reset_mock()
    jjm_check.reset_mock()

    # check, no args
    result = runner.invoke(jjm, ["check"])
    assert log.getEffectiveLevel() == logging.INFO
    assert result.exit_code == 0
    assert "ERROR" not in result.output
    JenkinsJobManager.assert_called_with(overrides_none)
    jjm_check.assert_not_called()
    check_auth.assert_not_called()
    handle_validation_errors.assert_called_once_with(JenkinsJobManager())
    handle_plan_report.assert_not_called()
    JenkinsJobManager.reset_mock()
    check_auth.reset_mock()
    handle_plan_report.reset_mock()
    handle_validation_errors.reset_mock()
    jjm_check.reset_mock()

    # check, all args
    result = runner.invoke(jjm, base_args + ["check", "--load-plugins"])
    assert log.getEffectiveLevel() == logging.DEBUG
    assert result.exit_code == 0
    assert "ERROR" not in result.output
    JenkinsJobManager.assert_called_once_with(overrides_url)
    jjm_check.assert_not_called()
    jjm_check.assert_not_called()
    check_auth.assert_not_called()
    handle_plan_report.assert_not_called()
    handle_validation_errors.assert_called_once_with(JenkinsJobManager())
    JenkinsJobManager.reset_mock()
    check_auth.reset_mock()
    handle_plan_report.reset_mock()
    handle_validation_errors.reset_mock()
    jjm_check.reset_mock()

    # import, no args
    result = runner.invoke(jjm, ["import"])
    assert log.getEffectiveLevel() == logging.DEBUG
    assert result.exit_code == 0
    assert "ERROR" not in result.output
    assert "Imported 0 jobs." in result.output
    JenkinsJobManager.assert_called_once_with(overrides_none)
    jjm_check.assert_not_called()
    check_auth.assert_called_once_with(JenkinsJobManager())
    handle_validation_errors.assert_not_called()
    handle_plan_report.assert_not_called()
    JenkinsJobManager.reset_mock()
    check_auth.reset_mock()
    handle_plan_report.reset_mock()
    handle_validation_errors.reset_mock()
    jjm_check.reset_mock()

    # login, no args
    result = runner.invoke(jjm, ["login"])
    assert log.getEffectiveLevel() == logging.DEBUG
    assert result.exit_code == 1
    assert "ERROR" not in result.output
    assert "Auth already configured for this jenkins" in result.output
    JenkinsJobManager.assert_called_once_with(overrides_none)
    jjm_check.assert_not_called()
    check_auth.assert_not_called()
    handle_validation_errors.assert_not_called()
    handle_plan_report.assert_not_called()
    JenkinsJobManager.reset_mock()
    check_auth.reset_mock()
    handle_plan_report.reset_mock()
    handle_validation_errors.reset_mock()
    jjm_check.reset_mock()

    # plan, no args
    result = runner.invoke(jjm, ["plan"])
    assert log.getEffectiveLevel() == logging.DEBUG
    assert result.exit_code == 2
    assert "ERROR" not in result.output
    JenkinsJobManager.assert_called_once_with(overrides_none)
    jjm_check.assert_not_called()
    check_auth.assert_called_once_with(JenkinsJobManager())
    handle_validation_errors.assert_called_once_with(JenkinsJobManager())
    handle_plan_report.assert_called_once_with(JenkinsJobManager(), use_pager=True)
    JenkinsJobManager.reset_mock()
    check_auth.reset_mock()
    handle_plan_report.reset_mock()
    handle_validation_errors.reset_mock()
    jjm_check.reset_mock()
