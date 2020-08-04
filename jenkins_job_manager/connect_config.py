import configparser
import hashlib
import logging
import os
import shlex

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jjm")


class JenkinsConnectConfig:
    """
    Handle jenkins connection config.
    Includes methods for loading/storing per-user, per-url auth config.
    """

    global_conf_path = "/etc/jjm/jenkins_creds.ini"
    user_conf_path = os.path.expanduser("~/.config/jjm/jenkins_creds.ini")
    __slots__ = ("url", "username", "password", "timeout", "metadata")

    def __init__(self, url, username, password, timeout=None, metadata=None):
        if url is not None and url.endswith("/"):
            url = url[:-1]
        self.url = url
        self.username, self.password = username, password
        self.timeout = int(timeout or 60)
        self.metadata = metadata or MetadataConfig({})

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
                "./jjm.ini",
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
        metadata = MetadataConfig.build_from_configparser(cp)

        def _section_by_url(key):
            return cp.get(url, key, fallback=None) or cp.get(
                "jenkins", key, fallback=None
            )

        loaded_config = JenkinsConnectConfig(
            url=url,
            username=_section_by_url("username"),
            password=_section_by_url("password"),
            timeout=_section_by_url("timeout"),
            metadata=metadata,
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


class MetadataConfig:
    """
    Jenkins metadata plugin has been dead for a while,
    so this is a hack to the description field to deal with it.
    """

    __slots__ = ("metadata_conf", "required_fields", "valid_field_values")

    def __init__(self, metadata_conf: dict):
        self.metadata_conf = metadata_conf
        self.required_fields = (
            self.metadata_conf.get("required-description-fields") or []
        )
        self.valid_field_values = {}
        for field in self.required_fields:
            key = f"valid-values-for-{field}".lower()
            if key in self.metadata_conf:
                self.valid_field_values[field] = self.metadata_conf[key]
        log.debug("required_fields: %r", self.required_fields)
        log.debug("valid_field_values: %r", self.valid_field_values)

    @staticmethod
    def build_from_configparser(cp: configparser.RawConfigParser):
        if not cp.has_section("metadata"):
            return None
        md_conf = {}
        for key, val in cp.items(section="metadata"):
            if (
                key.startswith("valid-values-for-")
                or key == "required-description-fields"
            ):
                val = shlex.split(val)
            md_conf[key] = val
        return MetadataConfig(md_conf)

    def validate(self, md: dict):
        for field in self.required_fields:
            if field not in md:
                yield (
                    f"Missing metadata in job description: {field}."
                    f"\nAdd a line like `{field}: somevalue` to the description."
                )
        for field, field_values in self.valid_field_values.items():
            val = md.get(field)
            if val is None:
                continue
            if val not in field_values:
                yield (
                    f"Field {field} in job description has invalid value {val}."
                    f"\nValid values are {','.join(field_values)}"
                )
