"""
Contains extensions for raw xml loading with jjb
"""
import os
import logging
import jinja2
import xml.etree.ElementTree as ET
import jenkins_jobs.modules.base
from jenkins_jobs.xml_config import XmlJob, XmlJobGenerator

log = logging.getLogger("jjm")


def load_xml_escaped(path):
    """shorthand function to work around some known issues with escaping from includes"""
    with open(path) as fp:
        contents = fp.read()
    return jinja2.filters.do_forceescape(contents)


# initialize a global jinja env
jenv = jinja2.Environment(
    loader=jinja2.FileSystemLoader(searchpath=(os.curdir,)),
    autoescape=True,
    undefined=jinja2.StrictUndefined,
)
jenv.globals["load_xml_escaped"] = load_xml_escaped


class RawXmlProject(jenkins_jobs.modules.base.Base):
    """add a job type for raw xml"""

    jenv = jenv

    def root_xml(self, data):
        name = data["name"]
        xmlstr = data["raw"]
        # add in a hack for raw jobs to do optional jinja templating
        if data.get("jinja") is True:
            log.debug("Rendering jinja template for %s", name)
            templ = self.jenv.from_string(xmlstr)
            xmlstr = templ.render(data=data)
            log.debug("rendered: \n---\n%s\n---", xmlstr)
        xml_parent = ET.fromstring(xmlstr)
        return xml_parent


class XmlJobGeneratorWithRaw(XmlJobGenerator):
    """bypasses the module loader for the raw xml job type"""

    def _annotate_with_plugins(self, xml_job: XmlJob):
        """Many elements coming out of jjb are missing plugin version data."""
        plugins: dict = self.registry.plugins_dict
        doc: ET.Element = xml_job.xml
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
