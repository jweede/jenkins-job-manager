import unittest.mock as mock
import pytest

from jenkins_job_manager.xml_change import (
    CREATE,
    UPDATE,
    DELETE,
    XmlChange,
    XmlChangeDefaultDict,
)


def test_XmlChangeDefaultDict():
    # merely tests that `__missing__` does what we expect
    xcdd = XmlChangeDefaultDict()
    assert isinstance(xcdd, dict)

    xc = xcdd["something"]
    assert xc.name == "something"


def test_XmlChange():
    with pytest.raises(TypeError):
        XmlChange()
    assert XmlChange("something")

    with pytest.raises(ValueError):
        XmlChange(None)

    xc = XmlChange(name="test")
    assert xc.name == "test"
    assert xc.before_xml is None
    assert xc.after_xml is None

    with mock.patch.object(
        XmlChange, attribute="xml_normalize", return_value="bar"
    ) as xn_mock:
        xc = XmlChange(name="test")
        s = "<foo/>"
        xc.before_xml = s
        xn_mock.assert_called_once_with(s)
        assert xc.before_xml == "bar"
        xn_mock.reset_mock()

        xc.after_xml = s
        xn_mock.assert_called_once_with(s)
        assert xc.after_xml == "bar"
        xn_mock.reset_mock()


_changetype_params = (
    (CREATE, None, "<project/>"),
    (DELETE, "<project/>", None),
    (None, "<project></project>", "<project/>"),
    (UPDATE, "<project><nope/></project>", "<project/>"),
    (UPDATE, "<porject/>", "<project/>"),
)


@pytest.mark.parametrize("changetype,before,after", _changetype_params)
def test_XmlChange_changetype(before, after, changetype):
    xc = XmlChange("something")
    if before is not None:
        xc.before_xml = before
    if after is not None:
        xc.after_xml = after
    assert xc.changetype() is changetype


_difflines_params = (
    (
        "death of a salesman",
        "<project/>",
        "<project><something>Nobody</something></project>",
        """\
--- death of a salesman

+++ death of a salesman

@@ -1,2 +1,4 @@

 <?xml version="1.0" ?>
-<project/>
+<project>
+  <something>Nobody</something>
+</project>
""",
    ),
)


@pytest.mark.parametrize("name,before,after,result", _difflines_params)
def test_XmlChange_difflines(name, before, after, result):
    """sanity check difflines"""
    xc = XmlChange(name)
    if before is not None:
        xc.before_xml = before
    if after is not None:
        xc.after_xml = after
    rendered = "\n".join(xc.difflines())
    expected_lines = result.rstrip()
    assert rendered == expected_lines
