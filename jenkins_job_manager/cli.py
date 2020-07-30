#!/usr/bin/env python3
"""
Tool for managing jenkins jobs through jenkins job builder
"""
import configparser
import difflib
import hashlib
import itertools
import logging
import os
import xml.dom.minidom
import xml.etree.ElementTree
from collections import defaultdict
from typing import Dict, Optional
from xml.dom import Node

import click
import jenkins
import jenkins_jobs.modules.base
import jinja2
from jenkins_jobs.parser import YamlParser
from jenkins_jobs.registry import ModuleRegistry
from jenkins_jobs.xml_config import XmlJob, XmlJobGenerator, XmlViewGenerator

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jjb")

HERE = os.path.dirname(os.path.realpath(__file__))
# constants used for enums herein
CREATE, UPDATE, DELETE = "create", "update", "delete"


class JenkinsConnectConfig:
    """
    Handle jenkins connection config.
    Includes methods for loading/storing per-user, per-url auth config.
    """

    global_conf_path = "/etc/jjb/jenkins_creds.ini"
    user_conf_path = os.path.expanduser("~/.config/jjb/jenkins_creds.ini")
    __slots__ = ("url", "username", "password", "timeout")

    def __init__(self, url, username, password, timeout=None):
        if url is not None and url.endswith("/"):
            url = url[:-1]
        self.url = url
        self.username, self.password = username, password
        self.timeout = int(timeout or 60)

    def __str__(self):
        return (
            f"(url={self.url} username={self.username}"
            f" password={self.password_obscured} timeout={self.timeout})"
        )

    def __repr__(self):
        props = ",".join(f"{slot}={getattr(self, slot)!r}" for slot in self.__slots__)
        _repr = f"{self.__class__.__name__}({props})"
        return _repr

    @property
    def password_obscured(self):
        if self.password is None:
            return None
        return "md5:" + hashlib.md5(self.password).hexdigest()

    @staticmethod
    def load_from_files(config_overrides=None):
        """loads config files in order, handles desired override structure"""
        cp = configparser.RawConfigParser()
        read_files = cp.read(
            [
                JenkinsConnectConfig.global_conf_path,
                JenkinsConnectConfig.user_conf_path,
                "./jjb.ini",
            ]
        )
        # cli overrides
        if config_overrides is not None:
            cp.read_dict({"jenkins": config_overrides})
        log.debug("loaded config: %r", read_files)
        url = cp.get("jenkins", "url", fallback=None)
        if not url:
            log.warning("Jenkins url not set.")
        elif url.endswith("/"):
            url = url[:-1]

        def _section_by_url(key):
            return cp.get(url, key, fallback=None) or cp.get("jenkins", key, fallback=None)

        loaded_config = JenkinsConnectConfig(
            url=url,
            username=_section_by_url("username"),
            password=_section_by_url("password"),
            timeout=_section_by_url("timeout"),
        )
        log.debug("loaded config=%r", loaded_config)
        return loaded_config

    def update_user_conf_auth(self, username, password):
        """create/update user config with auth values per url"""
        cp = configparser.RawConfigParser()
        cp.read([self.user_conf_path])
        if not cp.has_section(self.url):
            cp.add_section(self.url)
        cp.set(self.url, "username", username)
        cp.set(self.url, "password", password)
        os.makedirs(os.path.dirname(self.user_conf_path), exist_ok=True)
        with open(self.user_conf_path, "w") as fp:
            cp.write(fp)


class XmlChange:
    """Represents an xml job/view with current and new state."""

    __slots__ = ("name", "_before", "_after")

    def __init__(self, name):
        self.name = name
        if name is None:
            raise ValueError("Name must be set")
        self._before = None
        self._after = None

    @staticmethod
    def xml_normalize(xml_str: str) -> str:
        """Normalize xml by running through a parser and removing blank text elements."""
        root = xml.dom.minidom.parseString(xml_str)
        # remove blanks
        node_queue = [root]
        while node_queue:
            node = node_queue.pop()
            for n in node.childNodes:
                if n.nodeType is Node.TEXT_NODE and n.nodeValue:
                    n.nodeValue = n.nodeValue.strip()
                elif n.nodeType is Node.ELEMENT_NODE:
                    node_queue.append(n)

        root.normalize()
        return root.toprettyxml(indent="  ")

    def changetype(self):
        if self._before == self._after:
            # No change
            ret = None
        elif not self._before and self._after:
            ret = CREATE
        elif self._before and not self._after:
            ret = DELETE
        else:
            ret = UPDATE
        return ret

    def difflines(self):
        difflines = difflib.unified_diff(
            (self._before or "").splitlines(),
            (self._after or "").splitlines(),
            fromfile=self.name,
            tofile=self.name,
        )
        return difflines

    @property
    def before_xml(self):
        return self._before

    @property
    def after_xml(self):
        return self._after

    @before_xml.setter
    def before_xml(self, val):
        self._before = self.xml_normalize(val)

    @after_xml.setter
    def after_xml(self, val):
        self._after = self.xml_normalize(val)


class XmlChangeDefaultDict(defaultdict):
    def __missing__(self, key):
        val = XmlChange(name=key)
        self[key] = val
        return val


class JenkinsJobManager:
    """main jjb manager"""

    __slots__ = ("config", "plugins_list", "_jenkins", "jobs", "views")
    job_managing_job_classes = frozenset(["jenkins.branch.OrganizationFolder"])

    def __init__(self, config_overrides=None):

        self.config: JenkinsConnectConfig = JenkinsConnectConfig.load_from_files(config_overrides)
        self._jenkins: Optional[jenkins.Jenkins] = None
        self.plugins_list: Optional[list] = None
        self.jobs: Dict[str, XmlChange] = XmlChangeDefaultDict()
        self.views: Dict[str, XmlChange] = XmlChangeDefaultDict()

    @property
    def jenkins(self):
        if self._jenkins is None:
            self._jenkins = jenkins.Jenkins(
                url=self.config.url,
                username=self.config.username,
                password=self.config.password,
                timeout=self.config.timeout,
            )
        return self._jenkins

    def check_authentication(self):
        log.debug("checking credentials")
        try:
            self.jenkins.run_script("println 'ok'")
        except (jenkins.BadHTTPException, jenkins.JenkinsException) as e:
            log.debug("BadHTTPException: %s", e)
            return False
        return True

    def read_jobs(self):
        jenkins = self.jenkins
        jobs = self.jobs
        log.info("Reading jenkins jobs state")
        # ignorable subfolder jobs
        managed_job_urls = set()
        _empty = tuple()
        for d in jenkins.get_all_jobs():
            log.debug("found job %r", d)
            name, url, _class = d["fullname"], d["url"], d["_class"]
            subjobs = d.get("jobs", _empty)
            if _class in self.job_managing_job_classes:
                managed_job_urls.update(job_d["url"] for job_d in subjobs)
            elif url in managed_job_urls:
                log.debug("Ignoring managed job %s", name)
                # recursively ignore jobs of ignored jobs
                managed_job_urls.update(job_d["url"] for job_d in subjobs)
                continue
            job_conf = jenkins.get_job_config(name)
            jobs[name].before_xml = job_conf

    def load_plugins_list(self):
        """load plugin info in format expected by jjb libs"""
        log.debug("reading jenkins plugins")
        self.plugins_list = list(self.jenkins.get_plugins().values())

    @staticmethod
    def xml_dump(root: xml.etree.ElementTree.Element) -> str:
        return xml.etree.ElementTree.tostring(root, encoding="unicode")

    def generate_jjb_xml(self):
        """borrow jjb rendering to render jjb yaml to xml"""

        class JJBConfig:
            yamlparser = {
                "allow_duplicates": False,
                "keep_descriptions": True,
                "include_path": ".",
                "retain_anchors": None,
            }

        class RawXmlJob(jenkins_jobs.modules.base.Base):
            """add a job type for raw xml"""

            def root_xml(self, data):
                xml_parent = xml.etree.ElementTree.fromstring(data["raw"])
                return xml_parent

        class XmlJobGeneratorWithRaw(XmlJobGenerator):
            """bypasses the module loader for the raw xml job type"""

            def _getXMLForData(self, data):
                kind = data.get(self.kind_attribute, self.kind_default)
                if kind == "raw":
                    mod = RawXmlJob(self.registry)
                    _xml = mod.root_xml(data)
                    obj = XmlJob(_xml, data["name"])
                    return obj
                return super(XmlJobGenerator, self)._getXMLForData(data)

        options_names = []
        files_path = ["."]

        parser = YamlParser(JJBConfig)
        registry = ModuleRegistry(JJBConfig, self.plugins_list)

        xml_job_generator = XmlJobGeneratorWithRaw(registry)
        xml_view_generator = XmlViewGenerator(registry)

        parser.load_files(files_path)
        registry.set_parser_data(parser.data)

        job_data_list, view_data_list = parser.expandYaml(registry, options_names)

        xml_jobs = xml_job_generator.generateXML(job_data_list)
        jobs = self.jobs
        for xml_job in xml_jobs:
            jobs[xml_job.name].after_xml = self.xml_dump(xml_job.xml)

        xml_views = xml_view_generator.generateXML(view_data_list)
        views = self.views
        for xml_view in xml_views:
            views[xml_view.name].after_xml = self.xml_dump(xml_view.xml)

    def detected_changes(self):
        return any(
            item.changetype() is not None
            for item in itertools.chain(self.jobs.values(), self.views.values())
        )

    def gather(self):
        """run this to gather plan/apply data"""
        self.read_jobs()
        self.load_plugins_list()
        self.generate_jjb_xml()

    def plan_report(self):
        """report on changes about to be made"""
        template = jinja2.Template(
            """\
{% for difflines in obj.views %}{% for line in difflines -%}
{{ line }}
{% endfor %}{% endfor -%}
{% for difflines in obj.jobs %}{% for line in difflines -%}
{{ line }}
{% endfor %}{% endfor -%}
{% set created, updated, deleted = obj.changecounts[CREATE], obj.changecounts[UPDATE], obj.changecounts[DELETE] -%}
{% if created or updated or deleted %}
Jobs/Views added {{ created }}, updated {{ updated }}, removed {{ deleted }}.
{% else -%}
No changes.
{% endif -%}
""",
            undefined=jinja2.StrictUndefined,
        )

        changecounts = {CREATE: 0, UPDATE: 0, DELETE: 0}

        def iter_changes(xml_dict):
            """closure to handle changecount side effect"""
            for item in xml_dict.values():
                changetype = item.changetype()
                if changetype is None:
                    continue
                changecounts[changetype] += 1
                yield item.difflines()

        report_context = {
            "views": iter_changes(self.views),
            "jobs": iter_changes(self.jobs),
            "changecounts": changecounts,
            "CREATE": CREATE,
            "UPDATE": UPDATE,
            "DELETE": DELETE,
        }
        return template.generate(obj=report_context, CREATE=CREATE, UPDATE=UPDATE, DELETE=DELETE)

    def apply_plan(self):
        """apply changes from gather/plan"""
        changecounts = {CREATE: 0, UPDATE: 0, DELETE: 0}
        log.debug("applying views")
        for view in self.views.values():
            changetype = view.changetype()
            if changetype is None:
                log.debug("no change: %s", view.name)
                continue
            elif changetype is CREATE:
                log.info("create view %s", view.name)
                self.jenkins.create_view(view.name, view.after_xml)
                changecounts[CREATE] += 1
            elif changetype is UPDATE:
                log.info("reconfig view %s", view.name)
                self.jenkins.reconfig_view(view.name, view.after_xml)
                changecounts[UPDATE] += 1
            elif changetype is DELETE:
                log.info("delete view %s", view.name)
                self.jenkins.delete_view(view.name)
                changecounts[DELETE] += 1
            else:
                raise RuntimeError(f"Invalid changetype {changetype}(id={id(changetype)})")
        log.debug("applying jobs")
        for job in self.jobs.values():
            changetype = job.changetype()
            if changetype is None:
                log.debug("no change: %s", job.name)
                continue
            elif changetype is CREATE:
                log.info("create job %s", job.name)
                self.jenkins.create_job(job.name, job.after_xml)
                changecounts[CREATE] += 1
            elif changetype is UPDATE:
                log.info("reconfig job %s", job.name)
                self.jenkins.reconfig_job(job.name, job.after_xml)
                changecounts[UPDATE] += 1
            elif changetype is DELETE:
                log.info("delete job %s", job.name)
                self.jenkins.delete_job(job.name)
                changecounts[DELETE] += 1
            else:
                raise RuntimeError(f"Invalid changetype {changetype}(id={id(changetype)})")
        return changecounts


@click.group()
@click.option("--debug", "-d", is_flag=True)
@click.option("--working-dir", "-C", default=None, help="change to this directory ")
@click.option("--url", help="jenkins base url")
@click.pass_context
def jjb(ctx, debug, working_dir, url):
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
            "Create a ./jjb.ini file with contents:\n"
            "    [jenkins]\n"
            "    url = https://yourjenkinsurl.com/\n"
        )
        raise click.exceptions.Exit(1)


@jjb.command(name="login")
@click.pass_obj
def jjb_login(obj: JenkinsJobManager):
    """store login config per url"""
    jjm = obj
    jconf = jjm.config
    jurl = jconf.url
    username, password = jconf.username, jconf.password
    if username and password:
        click.secho(f"Auth already configured for this jenkins!", fg="red")
        click.secho(f"{jconf}", fg="white")
        click.confirm("overwrite?", abort=True)

    click.secho("Configuring login info for:", fg="green")
    click.secho(f"\t{jurl}", fg="white")

    click.secho(f"\nEnter username, go to {jurl}/whoAmI/ if unsure.")
    username = click.prompt("username", type=str)

    click.secho(f"\nEnter api key. go to {jurl}/user/{username}/configure to make a new one.")
    password = click.prompt("api key", type=str, hide_input=True)
    log.debug("entered username=%r password=%r", username, password)

    jconf.username, jconf.password = username, password
    if jjm.check_authentication():
        click.secho(f"Success! Saving to {jconf.user_conf_path}", fg="green")
        jconf.update_user_conf_auth(username, password)
    else:
        click.secho(f"Bad Authentication, try again.", fg="red")
        raise click.exceptions.Exit(2)


@jjb.command(name="check")
@click.pass_obj
def jjb_check(obj: JenkinsJobManager):
    """check syntax/config"""
    obj.generate_jjb_xml()


@jjb.command(name="test")
@click.pass_obj
def jjb_test(obj: JenkinsJobManager):
    """check syntax/config"""
    obj.gather()
    print(obj.detected_changes())
    for item in obj.jobs.values():
        print(item.name, item.changetype())


def check_auth(obj: JenkinsJobManager):
    """cli helper for auth check"""
    if not obj.check_authentication():
        click.secho(f"Bad login detected for {obj.config}", fg="red")
        click.echo("Try the login subcommand")
        raise click.exceptions.Exit(1)


def handle_plan_report(obj: JenkinsJobManager, use_pager=True):
    """cli helper for plan report"""

    def output_format(line):
        if line.startswith("+"):
            return click.style(line, fg="green")
        elif line.startswith("-"):
            return click.style(line, fg="red")
        else:
            return line

    if obj.detected_changes():
        gen_lines = map(output_format, obj.plan_report())
        if use_pager is True:
            click.echo_via_pager(gen_lines)
        else:
            for line in gen_lines:
                click.echo(line, nl=False)
    else:
        click.secho("No changes.", fg="green")


@jjb.command(name="plan")
@click.pass_obj
def jjb_plan(obj: JenkinsJobManager):
    """check syntax/config"""
    check_auth(obj)
    obj.gather()
    handle_plan_report(obj, use_pager=True)


@jjb.command(name="apply")
@click.pass_obj
def jjb_apply(obj: JenkinsJobManager):
    """check and apply changes"""
    check_auth(obj)
    obj.gather()
    if not obj.detected_changes():
        click.secho("No changes to apply.", fg="green")
        return
    handle_plan_report(obj, use_pager=False)
    click.confirm(click.style("Apply changes?", bold=True), abort=True)
    changecounts = obj.apply_plan()
    click.echo(
        f"Changes applied. added={changecounts[CREATE]} updated={changecounts[UPDATE]}"
        f" deleted={changecounts[DELETE]}"
    )


if __name__ == "__main__":
    jjb()
