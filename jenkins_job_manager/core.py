from jenkins_job_manager.connect_config import JenkinsConnectConfig
from jenkins_job_manager.xml_change import (
    XmlChange,
    XmlChangeDefaultDict,
    CREATE,
    UPDATE,
    DELETE,
)
from jenkins_job_manager.raw_ext import (
    RawXmlProject,
    XmlJobGeneratorWithRaw,
)

import fnmatch
import glob
import itertools
import logging
import os
import random
import re
import string
import xml.etree.ElementTree as ET
from typing import Dict, Optional

import jenkins
import jinja2
from jenkins_jobs.parser import YamlParser
from jenkins_jobs.registry import ModuleRegistry
from jenkins_jobs.xml_config import XmlJob, XmlViewGenerator

HERE = os.path.dirname(os.path.realpath(__file__))
J2_DIR = f"{HERE}/j2_templates"

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jjm")


class NameRegexFilter:
    """Regex Filter Callable"""

    __slots__ = ("regex",)

    def __init__(self, regexp):
        self.regex = re.compile(regexp)

    @staticmethod
    def from_glob_list(globs):
        regexes = map(fnmatch.translate, globs)
        combined_regex = "|".join(regexes)
        return NameRegexFilter(combined_regex)

    def __call__(self, job_name):
        m = self.regex.match(job_name)
        return True if m is not None else False

    def __repr__(self):
        return f"{self.__class__.__name__}<{repr(self.regex)[11:-1]}>"


class JenkinsJobManager:
    """main jjb manager"""

    __slots__ = (
        "config",
        "plugins_list",
        "_jenkins",
        "jobs",
        "_jobs_filter_func",
        "views",
        "validation_errors",
        "jenv",
    )
    job_managing_job_classes = frozenset(["jenkins.branch.OrganizationFolder"])
    raw_xml_yaml_path = "./raw_xml_jobs.yaml"

    def __init__(self, config_overrides=None):
        self.config: JenkinsConnectConfig = JenkinsConnectConfig.load_from_files(
            config_overrides
        )
        self._jenkins: Optional[jenkins.Jenkins] = None
        self.plugins_list: Optional[list] = None
        self.jobs: Dict[str, XmlChange] = XmlChangeDefaultDict()
        self._jobs_filter_func: NameRegexFilter = NameRegexFilter(".*")
        self.views: Dict[str, XmlChange] = XmlChangeDefaultDict()
        self.validation_errors = []
        self.jenv = jinja2.Environment(
            loader=jinja2.FileSystemLoader([J2_DIR]),
            undefined=jinja2.StrictUndefined,
            autoescape=False,
        )

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
        """check if jenkins connection config correct"""
        log.debug("checking credentials")
        try:
            result = self.jenkins.get_whoami()
            if self.config.username != result["id"]:
                raise RuntimeError(f"{self.config.username!r} != {result['id']!r}")
        except (jenkins.BadHTTPException, jenkins.JenkinsException) as e:
            log.debug("BadHTTPException: %s", e)
            return False
        return True

    def read_views(self):
        """read existing views from jenkins"""
        jenkins = self.jenkins
        views = self.views
        log.info("Reading jenkins views state")

        for view_d in jenkins.get_views():
            log.debug("found view %r", view_d)
            name, url, _class = view_d["name"], view_d["url"], view_d.get("_class")
            if not self._jobs_filter_func(name):
                log.debug("Ignored by filter: %s", name)
                continue
            if name == "All" or name == "all" or _class == "hudson.model.AllView":
                log.debug("ignoring AllView: %r", view_d)
                continue
            view_config = jenkins.get_view_config(name)
            views[name].before_xml = view_config

    def read_jobs(self):
        """read existing jobs from jenkins"""
        jenkins = self.jenkins
        jobs = self.jobs

        log.info("Reading jenkins jobs state")
        # ignorable subfolder jobs
        managed_job_urls = set()
        _empty = tuple()
        for d in jenkins.get_all_jobs():
            log.debug("found job %r", d)
            name, url, _class = d["fullname"], d["url"], d.get("_class")
            subjobs = d.get("jobs", _empty)
            if not self._jobs_filter_func(name):
                log.debug("Ignored by filter: %s", name)
                continue
            elif _class in self.job_managing_job_classes:
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
    def xml_dump(root: ET.Element) -> str:
        return ET.tostring(root, encoding="unicode")

    def get_jjb_config(self):
        class JJBConfig:
            yamlparser = {
                "allow_duplicates": False,
                "keep_descriptions": True,
                "include_path": ".",
                "retain_anchors": None,
            }

            @staticmethod
            def get_plugin_config(*args, **kwargs):
                return None

        return JJBConfig

    def jenkins_format_xml(self, xml_job: XmlJob):
        """
        bounces job config through jenkins to get the formatting right
        unused, deprecated
        """
        jenkins = self.jenkins
        _xml: ET.Element = xml_job.xml

        if not _xml.find("./disabled"):
            d = ET.Element("disabled")
            d.text = "false"
            _xml.append(d)
        disabled_job = _xml.find("./disabled").text == "true"

        rand_suffix = "".join(random.choice(string.hexdigits) for _ in range(10))
        tmp_name = f"zz_jjm_tmp_{xml_job.name}_{rand_suffix}"
        tmp_xml = xml_job.xml
        tmp_xml.find("./disabled").text = "true"
        tmp_xml_str = ET.tostring(tmp_xml, encoding="unicode")
        log.info("creating %s", tmp_name)
        jenkins.create_job(tmp_name, tmp_xml_str)
        formatted_xml = jenkins.get_job_config(tmp_name)
        log.info("removing %s", tmp_name)
        jenkins.delete_job(tmp_name)
        if not disabled_job:
            formatted_xml = formatted_xml.replace(
                "<disabled>true</disabled>", "<disabled>false</disabled>"
            )
        return formatted_xml

    def generate_jjb_xml(self):
        """render jjb yaml to xml"""

        jjb_config = self.get_jjb_config()
        options_names = []  # normally a list of jobs globs for targeting
        files_path = glob.glob("./**/", recursive=True)

        parser = YamlParser(jjb_config)
        registry = ModuleRegistry(jjb_config, self.plugins_list)

        xml_job_generator = XmlJobGeneratorWithRaw(registry)
        xml_view_generator = XmlViewGenerator(registry)

        parser.load_files(files_path)
        registry.set_parser_data(parser.data)

        job_data_list, view_data_list = parser.expandYaml(registry, options_names)

        def job_data_filter_wrapper(job_data):
            return self._jobs_filter_func(job_data["name"])

        xml_jobs = xml_job_generator.generateXML(
            filter(job_data_filter_wrapper, job_data_list)
        )
        jobs = self.jobs
        for xml_job in xml_jobs:
            formatted_xml_str = self.xml_dump(xml_job.xml)
            jobs[xml_job.name].after_xml = formatted_xml_str

        xml_views = xml_view_generator.generateXML(
            filter(job_data_filter_wrapper, view_data_list)
        )
        views = self.views
        for xml_view in xml_views:
            views[xml_view.name].after_xml = self.xml_dump(xml_view.xml)

    def detected_changes(self):
        return any(
            item.changetype() is not None
            for item in itertools.chain(self.jobs.values(), self.views.values())
        )

    def gather(self, target_job_names=None):
        """run this to gather plan/apply data"""
        if target_job_names:
            log.debug("target_job_names=%r", target_job_names)
            self._jobs_filter_func = NameRegexFilter.from_glob_list(target_job_names)
        self.read_views()
        self.read_jobs()
        self.load_plugins_list()
        self.generate_jjb_xml()

    def import_missing(self) -> list:
        """import missing jobs as xml"""
        missing = [item for item in self.jobs.values() if item.changetype() is DELETE]
        if not missing:
            return []

        class FakeRegistry:
            modules = []

        def job_name_to_file_name(j_name):
            _part = re.sub(r"[\/]", "_", j_name)
            return f"./{_part}.xml"

        xml_job_name_pairs = []

        if os.path.exists(self.raw_xml_yaml_path):
            parser = YamlParser(self.get_jjb_config())
            parser.load_files([self.raw_xml_yaml_path])
            job_data_list, _ = parser.expandYaml(FakeRegistry, [])
            for job_data in job_data_list:
                name = job_data["name"]
                fname = job_name_to_file_name(name)
                assert os.path.exists(fname)
                xml_job_name_pairs.append((name, fname))
        template = self.jenv.get_template("raw_xml_import.j2")

        for mxml in missing:
            job_name = mxml.name
            file_name = job_name_to_file_name(job_name)
            job_config = mxml.before_xml
            xml_job_name_pairs.append((job_name, file_name))
            assert not os.path.exists(file_name)
            with open(file_name, "w") as fp:
                fp.write(job_config)
            log.info("Imported %s to %s", job_name, file_name)

        with open(self.raw_xml_yaml_path, "w") as fp:
            template.stream(raw_xml_jobs=xml_job_name_pairs).dump(fp)
        return missing

    def validate_metadata(self):
        md_conf = self.config.metadata

        for job in self.jobs.values():
            if job.after_xml is None:
                continue
            md = job.extract_md()
            warnings = md_conf.validate(md)
            for warning in warnings:
                yield job.name, warning

    def plan_report(self, report_format=None):
        """report on changes about to be made"""
        if report_format == "json":
            template_name = "json.j2"
        elif report_format == "yaml":
            template_name = "yaml.j2"
        else:
            template_name = "default.j2"
        template = self.jenv.get_template(template_name)

        changecounts = {CREATE: [], UPDATE: [], DELETE: []}

        def iter_changes(xml_dict, output=None):
            """closure to handle changecount side effect"""

            for item in xml_dict.values():
                changetype = item.changetype()
                if changetype is None:
                    continue
                if output:
                    md = item.extract_md() or {}
                    yield item.name, item.before_xml, item.after_xml, item.difflines(), md, item.changetype()
                else:
                    for i, line in enumerate(item.difflines()):
                        # deals with the rare case that the diff shows no lines
                        if i == 0:
                            changecounts[changetype].append(item.name)
                        yield line

        report_context = {
            "view_changes": iter_changes(self.views),
            "job_changes": iter_changes(self.jobs, report_format),
            "changecounts": changecounts,
        }

        return template.generate(
            obj=report_context, CREATE=CREATE, UPDATE=UPDATE, DELETE=DELETE
        )

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
                if self.config.allow_delete:
                    self.jenkins.delete_view(view.name)
                else:
                    log.warning("refusing to delete view %s", view.name)
                changecounts[DELETE] += 1
            else:
                raise RuntimeError(
                    f"Invalid changetype {changetype}(id={id(changetype)})"
                )
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
                if self.config.allow_delete:
                    self.jenkins.delete_job(job.name)
                else:
                    log.warning("refusing to delete job %s", job.name)
                changecounts[DELETE] += 1
            else:
                raise RuntimeError(
                    f"Invalid changetype {changetype}(id={id(changetype)})"
                )
        msg = (
            f"Changes applied. added={changecounts[CREATE]} updated={changecounts[UPDATE]}"
            f" deleted={changecounts[DELETE]}"
        )
        return changecounts, msg
