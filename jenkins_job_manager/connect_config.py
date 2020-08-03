import configparser
import hashlib
import logging
import os

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("jjm")


class JenkinsConnectConfig:
    """
    Handle jenkins connection config.
    Includes methods for loading/storing per-user, per-url auth config.
    """

    global_conf_path = "/etc/jjm/jenkins_creds.ini"
    user_conf_path = os.path.expanduser("~/.config/jjm/jenkins_creds.ini")
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

        def _section_by_url(key):
            return cp.get(url, key, fallback=None) or cp.get(
                "jenkins", key, fallback=None
            )

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
