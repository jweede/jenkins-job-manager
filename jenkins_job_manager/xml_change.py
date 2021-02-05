import difflib
import operator
import xml.dom.minidom
import xml.etree.ElementTree as ET
import re
import logging

from collections import defaultdict
from xml.dom import Node

# constants used for enums herein
CREATE, UPDATE, DELETE = "create", "update", "delete"
log = logging.getLogger("jjm")


class XmlChange:
    """Represents an xml job/view with current and new state."""

    __slots__ = ("name", "_before", "_after")

    sortable_node_names = {
        "project",
        "hudson.plugins.ws__cleanup.WsCleanup",
        "jenkins.plugins.slack.SlackNotifier",
    }

    def __init__(self, name: str):
        self.name = name
        if not name:
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

            if node.nodeName in XmlChange.sortable_node_names:
                # sort child elements for consistency
                node.childNodes.sort(key=operator.attrgetter("nodeName"))

            for n in node.childNodes:
                if n.nodeType is Node.TEXT_NODE and n.nodeValue:
                    n.nodeValue = n.nodeValue.strip()
                elif n.nodeType is Node.ELEMENT_NODE:
                    node_queue.append(n)

        root.normalize()
        return root.toprettyxml(indent="  ")

    def extract_md(self):
        if not self._after:
            return {}
        node = ET.fromstring(self._after)
        desc = node.find("./description")
        if desc is None or not desc.text:
            log.warning("No description in jenkins job %r??", self.name)
            return {}
        text = desc.text.replace("<!-- Managed by Jenkins Job Builder -->", "")
        md = {
            m.group(1): m.group(2)
            for m in re.finditer(r"^\s*([\w-]+):\s*([\w -]+)\s*$", text, flags=re.M)
        }
        return md

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
