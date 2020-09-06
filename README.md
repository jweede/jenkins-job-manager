# Jenkins Job Manager

This is a wrapper script around [Jenkins Job Builder][jjb], that adds:
 - jenkins login management
 - Preview of changes _before_ applying them, similar to [Terraform][tf].
 - A "raw" project type, so you can manage projects that [JJB][jjb] does not yet support.

## Installation

Will be published to pypi

## Usage

```
Usage: jjm [OPTIONS] COMMAND [ARGS]...

  Jenkins Job Management

Options:
  -d, --debug
  -C, --working-dir TEXT  change to this directory
  --url TEXT              jenkins base url
  --help                  Show this message and exit.

Commands:
  apply   check and apply changes
  check   check syntax/config
  import
  login   store creds per url
  plan    check syntax/config
```

The working-dir defaults to the current directory.

### `jjm login`

jjm expects every folder of configuration files to have a `jjm.ini` file with at least the following:

```
[jenkins]
url = https://yourjenkinsserver
```

Once this file exists, JJM's login will interactively ask for a user id and api key. These credentials will be stored in the user config file: `"~/.config/jjb/jenkins_creds.ini"`

The format looks like:

```
[https://jenkins1.example.com]
username = myuser
password = someapikey

[https://jenkins2.example.com]
username = myotheruser
password = someapikey
```

For most Jenkins setups the password will be an API key.
Both work, just remember this is stored unencrypted.

This should make managing multiple jenkins servers easier.

### `jjm check`

Check syntax, config.

### `jjm import`

Import existing jenkins jobs that are missing from the specified instance as raw xml.
A future release might assist by converting known modules to yaml.

### `jjm plan`

Shows changes that would be applied by a run.

### `jjm apply`

Preview and apply changes on confirmation.

## Contributing

Plz halp

[jjb]: https://docs.openstack.org/infra/jenkins-job-builder/
[tf]: https://www.terraform.io/
