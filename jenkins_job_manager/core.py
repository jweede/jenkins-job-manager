from jenkins_job_manager.connect_config import JenkinsConnectConfig
from jenkins_job_manager.xml_change import (
    XmlChange,
    XmlChangeDefaultDict,
    CREATE,
    UPDATE,
    DELETE,
)

import itertools
import logging
import os
import re
import random
import string
import xml.dom.minidom
import xml.etree.ElementTree
from typing import Dict, Optional

import jenkins
import jenkins_jobs.modules.base
import jinja2
from jenkins_jobs.parser import YamlParser
from jenkins_jobs.registry import ModuleRegistry
from jenkins_jobs.xml_config import XmlJob, XmlJobGenerator, XmlViewGenerator


logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jjm")


class JenkinsJobManager:
    """main jjb manager"""

    __slots__ = (
        "config",
        "plugins_list",
        "_jenkins",
        "jobs",
        "views",
        "validation_errors",
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
        self.views: Dict[str, XmlChange] = XmlChangeDefaultDict()
        self.validation_errors = []

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
            self.jenkins.run_script("println 'ok'")
        except (jenkins.BadHTTPException, jenkins.JenkinsException) as e:
            log.debug("BadHTTPException: %s", e)
            return False
        return True

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
        _xml: xml.etree.ElementTree.Element = xml_job.xml

        if not _xml.find("./disabled"):
            d = xml.etree.ElementTree.Element("disabled")
            d.text = "false"
            _xml.append(d)
        disabled_job = _xml.find("./disabled").text == "true"

        rand_suffix = "".join(random.choice(string.hexdigits) for _ in range(10))
        tmp_name = f"zz_jjm_tmp_{xml_job.name}_{rand_suffix}"
        tmp_xml = xml_job.xml
        tmp_xml.find("./disabled").text = "true"
        tmp_xml_str = xml.etree.ElementTree.tostring(tmp_xml, encoding="unicode")
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

        class RawXmlProject(jenkins_jobs.modules.base.Base):
            """add a job type for raw xml"""

            def root_xml(self, data):
                xml_parent = xml.etree.ElementTree.fromstring(data["raw"])
                return xml_parent

        class XmlJobGeneratorWithRaw(XmlJobGenerator):
            """bypasses the module loader for the raw xml job type"""

            def _annotate_with_plugins(self, xml_job: XmlJob):
                """Many elements coming out of jjb are missing plugin version data."""
                plugins: dict = self.registry.plugins_dict
                doc: xml.etree.ElementTree.Element = xml_job.xml
                for node in doc.iterfind(".//*[@plugin]"):
                    plugin_name = node.attrib["plugin"]
                    if "@" in plugin_name:
                        continue
                    version = plugins[plugin_name]["version"]
                    log.debug("annotated %r with %s@%s", node, plugin_name, version)
                    node.attrib["plugin"] = f"{plugin_name}@{version}"

            def _getXMLForData(self, data):
                kind = data.get(self.kind_attribute, self.kind_default)
                if kind == "raw":
                    mod = RawXmlProject(self.registry)
                    _xml = mod.root_xml(data)
                    obj = XmlJob(_xml, data["name"])
                    return obj
                xml_job = super(XmlJobGenerator, self)._getXMLForData(data)
                # self._annotate_with_plugins(xml_job)
                return xml_job

        jjb_config = self.get_jjb_config()
        options_names = []
        files_path = ["."]

        parser = YamlParser(jjb_config)
        registry = ModuleRegistry(jjb_config, self.plugins_list)

        xml_job_generator = XmlJobGeneratorWithRaw(registry)
        xml_view_generator = XmlViewGenerator(registry)

        parser.load_files(files_path)
        registry.set_parser_data(parser.data)

        job_data_list, view_data_list = parser.expandYaml(registry, options_names)

        xml_jobs = xml_job_generator.generateXML(job_data_list)
        jobs = self.jobs
        for xml_job in xml_jobs:
            formatted_xml_str = self.xml_dump(xml_job.xml)
            jobs[xml_job.name].after_xml = formatted_xml_str

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

    def import_missing(self):
        """import missing jobs as xml"""
        missing = [item for item in self.jobs.values() if item.changetype() is DELETE]
        if not missing:
            return None

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
        template = jinja2.Template(
            """\
---
{% for job_name, file_name in raw_xml_jobs -%}
- job:
   name: {{ job_name |tojson }}
   project-type: raw
   raw: !include-raw: {{ file_name }}

{% endfor -%}
""",
            undefined=jinja2.StrictUndefined,
        )

        for missing in missing:
            job_name = missing.name
            file_name = job_name_to_file_name(job_name)
            job_config = missing.before_xml
            xml_job_name_pairs.append((job_name, file_name))
            assert not os.path.exists(file_name)
            with open(file_name, "w") as fp:
                fp.write(job_config)
            log.info("Imported %s to %s", job_name, file_name)

        with open(self.raw_xml_yaml_path, "w") as fp:
            template.stream(raw_xml_jobs=xml_job_name_pairs).dump(fp)
        return missing

    def validate_metadata(self):
        ET = xml.etree.ElementTree
        md_conf = self.config.metadata

        def extract_md(job: XmlChange):
            node = ET.fromstring(job.after_xml)
            desc = node.find("./description")
            if desc is None:
                log.warning("No description in jenkins job %r??", job.name)
                return {}
            md = {
                m.group(1): m.group(2)
                for m in re.finditer(r"^([\w-]+):\s*([\w -]+)$", desc.text, flags=re.M)
            }
            return md

        for job in self.jobs.values():
            if job.after_xml is None:
                continue
            md = extract_md(job)
            warnings = md_conf.validate(md)
            for warning in warnings:
                yield job.name, warning

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
                self.jenkins.delete_view(view.name)
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
                self.jenkins.delete_job(job.name)
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
