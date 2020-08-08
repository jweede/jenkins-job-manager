import click.testing
import logging
from unittest import mock
from jenkins_job_manager import __version__
from jenkins_job_manager.cli import jjm, log


def test_version():
    assert __version__ == "0.2.4"

@mock.patch("jenkins_job_manager.cli.jjm_check", autospec=True)
@mock.patch("jenkins_job_manager.cli.JenkinsJobManager", autospec=True)
def test_jjm(jjm_check, JenkinsJobManager):
    runner = click.testing.CliRunner()
    base_args = ["-d", "-C", "/tmp", "--url", "https://yourjenkinsurl.com/"]
    config_overrides = {"url": "https://yourjenkinsurl.com/"}

    # no args (no command)
    result = runner.invoke(jjm)
    assert log.getEffectiveLevel() == logging.INFO
    assert result.exit_code == 0
    assert "Usage:" in result.output
    JenkinsJobManager.assert_not_called()
    JenkinsJobManager.reset_mock()

    # all args (no command)
    result = runner.invoke(jjm, base_args)
    assert log.getEffectiveLevel() == logging.INFO
    assert result.exit_code == 2
    assert "Usage:" in result.output
    JenkinsJobManager.assert_not_called()
    JenkinsJobManager.reset_mock()

    # apply, no args
    result = runner.invoke(jjm, ["apply"])
    assert log.getEffectiveLevel() == logging.INFO
    assert result.exit_code == 1
    assert "ERROR" not in result.output
    JenkinsJobManager.assert_not_called()
    JenkinsJobManager.reset_mock()

    # check, no args 
    result = runner.invoke(jjm, ["check"])
    assert log.getEffectiveLevel() == logging.INFO
    assert result.exit_code == 0
    assert "ERROR" not in result.output
    JenkinsJobManager.assert_not_called()
    JenkinsJobManager.reset_mock()

    # check, all args
    result = runner.invoke(jjm, base_args + ["check", "--load-plugins"])
    assert log.getEffectiveLevel() == logging.DEBUG
    assert result.exit_code == 0
    assert "ERROR" not in result.output
    JenkinsJobManager.assert_not_called()
    JenkinsJobManager.reset_mock()
    jjm_check.assert_called_with(config_overrides)
    jjm_check.reset_mock()

    # import, no args
    result = runner.invoke(jjm, ["import"])
    assert log.getEffectiveLevel() == logging.DEBUG
    assert result.exit_code == 0
    assert "ERROR" not in result.output
    assert "Imported 0 jobs." in result.output
    JenkinsJobManager.assert_not_called()
    JenkinsJobManager.reset_mock()


    # login, no args
    result = runner.invoke(jjm, ["login"])
    assert log.getEffectiveLevel() == logging.DEBUG
    assert result.exit_code == 1
    assert "ERROR" not in result.output
    assert "Auth already configured for this jenkins" in result.output
    JenkinsJobManager.assert_not_called()
    JenkinsJobManager.reset_mock()

    # plan, no args
    result = runner.invoke(jjm, ["plan"])
    assert log.getEffectiveLevel() == logging.DEBUG
    assert result.exit_code == 2
    assert "ERROR" not in result.output
    JenkinsJobManager.assert_not_called()
    JenkinsJobManager.reset_mock()

