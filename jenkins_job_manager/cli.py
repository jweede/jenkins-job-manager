#!/usr/bin/env python3
"""
Wrapper tool for managing jenkins jobs via jenkins job builder
"""
from jenkins_job_manager.core import JenkinsJobManager
from jenkins_job_manager.xml_change import DELETE

import click
import logging
import os
import typing

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jjm")

HERE = os.path.dirname(os.path.realpath(__file__))


click_option_target = click.option(
    "--target",
    default=None,
    multiple=True,
    help="job name glob to target",
)


@click.group()
@click.option("--debug", "-d", is_flag=True)
@click.option("--working-dir", "-C", default=None, help="change to this directory ")
@click.option("--url", help="jenkins base url")
@click.pass_context
def jjm(ctx, debug, working_dir, url):
    """Jenkins Job Management"""
    if debug:
        log.setLevel(logging.DEBUG)
    if working_dir:
        os.chdir(working_dir)

    config = {}
    if url:
        config["url"] = url
    jjm = JenkinsJobManager(config_overrides=config)
    ctx.obj = jjm
    if not jjm.config.url:
        click.echo(
            "\n"
            "ERROR: No jenkins url configured.\n"
            "Create a ./jjm.ini file with contents:\n"
            "    [jenkins]\n"
            "    url = https://yourjenkinsurl.com/\n"
        )
        raise click.exceptions.Exit(1)


@jjm.command(name="login")
@click.pass_obj
def jjm_login(obj: JenkinsJobManager):
    """store login config per url"""
    jjm = obj
    jconf = jjm.config
    jurl = jconf.url
    username, password = jconf.username, jconf.password
    if username and password:
        click.secho("Auth already configured for this jenkins!", fg="red")
        click.secho(f"{jconf}", fg="white")
        click.confirm("overwrite?", abort=True)

    click.secho("Configuring login info for:", fg="green")
    click.secho(f"\t{jurl}", fg="white")

    click.secho(
        f"\nEnter username, If unsure go to {jurl}/whoAmI/"
        f" (if this says anonymous, you need to login first)"
    )
    username = click.prompt("username", type=str)

    click.secho(
        f"\nEnter api key. go to {jurl}/user/{username}/configure to make a new one."
    )
    password = click.prompt("api key", type=str, hide_input=True)
    log.debug("entered username=%r password=%r", username, password)

    jconf.username, jconf.password = username, password
    if jjm.check_authentication():
        click.secho(f"Success! Saving to {jconf.user_conf_path}", fg="green")
        jconf.update_user_conf_auth(username, password)
    else:
        click.secho("Bad Authentication, try again.", fg="red")
        raise click.exceptions.Exit(2)


def handle_validation_errors(obj: JenkinsJobManager, ignore=False):
    warnings = obj.validate_metadata()
    errors = False
    for job_name, warning in warnings:
        if errors is False:
            click.secho("Validation Errors", fg="red", bold=True)
            errors = True
        click.secho(f"Job {job_name!r}: {warning}", fg="red")

    if errors is True and ignore is False:
        raise click.exceptions.Exit(5)


@jjm.command(name="check")
@click.option("--load-plugins", is_flag=True)
@click.pass_obj
def jjm_check(obj: JenkinsJobManager, load_plugins):
    """check syntax/config"""
    if load_plugins:
        obj.load_plugins_list()
    obj.generate_jjb_xml()
    handle_validation_errors(obj)


def check_auth(obj: JenkinsJobManager):
    """cli helper for auth check"""
    if not obj.check_authentication():
        click.secho(f"Bad login detected for {obj.config}", fg="red")
        click.echo("Try the login subcommand")
        raise click.exceptions.Exit(1)


def handle_plan_report(obj: JenkinsJobManager, use_pager=True, output=None) -> bool:
    """cli helper for plan report"""
    changes = obj.detected_changes()

    if output:
        # machine readable
        for line in obj.plan_report(report_format=output):
            click.echo(line, nl=False)
    elif changes:
        # default "human" readable, show changes
        def output_format(line):
            if line.startswith("+"):
                return click.style(line, fg="green")
            elif line.startswith("-"):
                return click.style(line, fg="red")
            else:
                return line

        gen_lines = map(output_format, obj.plan_report())
        if use_pager is True:
            click.echo_via_pager(gen_lines)
        else:
            for line in gen_lines:
                click.echo(line, nl=False)
    else:
        # default "human" readable, no changes
        click.secho("No changes.", fg="green")

    return changes


@jjm.command(name="plan")
@click.option("--skip-pager", is_flag=True)
@click.option(
    "--output", default=None, type=click.Choice(["json", "yaml"], case_sensitive=False)
)
@click_option_target
@click.pass_obj
def jjm_plan(
    obj: JenkinsJobManager,
    skip_pager: bool,
    output: typing.Optional[str],
    target: typing.List[str],
):
    """check for changes"""
    check_auth(obj)
    obj.gather(target)
    handle_validation_errors(obj)
    changes = handle_plan_report(obj, use_pager=not skip_pager, output=output)
    if changes is True:
        raise click.exceptions.Exit(2)


@jjm.command(name="apply")
@click.option("--allow-delete", is_flag=True, help="disables delete safety.")
@click.option("--auto-approve", is_flag=True, help="disables prompts.")
@click_option_target
@click.pass_obj
def jjm_apply(
    obj: JenkinsJobManager, target: str, auto_approve: bool, allow_delete: bool
):
    """check and apply changes"""
    if allow_delete:
        obj.config.allow_delete = True
    check_auth(obj)
    obj.gather(target)
    handle_validation_errors(obj)
    if obj.detected_changes() is False:
        click.secho("No changes to apply.", fg="green")
        return
    handle_plan_report(obj, use_pager=False)
    if not auto_approve:
        click.confirm(click.style("Apply changes?", bold=True), abort=True)
    changecounts, msg = obj.apply_plan()
    click.echo(msg)
    _deletes = changecounts[DELETE]
    if allow_delete is False and _deletes > 0:
        click.secho(
            f"Ignored {_deletes} deletes.\nUse --allow-delete to override.",
            fg="red",
        )


@jjm.command(name="import")
@click_option_target
@click.pass_obj
def jjm_import(obj: JenkinsJobManager, target: str):
    check_auth(obj)
    obj.gather(target)
    missing = obj.import_missing()
    click.secho(f"Imported {len(missing)} jobs.", fg="green")


if __name__ == "__main__":
    jjm()
