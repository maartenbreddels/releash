#!/usr/bin/env python
from __future__ import print_function
from contextlib import contextmanager
import hashlib
import imp
import os
import pkg_resources
import re
import shutil
import sys
import tempfile
import time

import semver

try:
    from urllib import urlretrieve  # py2
    HTTPError = Exception
except ImportError:
    from urllib.request import urlretrieve  # py3
    from urllib.error import HTTPError

__version_tuple__ = (0, 2, 0)
__version__ = '0.2.0'

try:
    input = raw_input  # py2/3
except NameError:
    pass

dry_run = False
force = False  # force commands, such as tagging
verbose = False
quiet = False
interactive = False
semver_bump = [semver.bump_major, semver.bump_minor,
               semver.bump_patch, semver.bump_prerelease, semver.bump_build]


_to_null = ' > nul 2>&1' if os.name == 'nt' else ' &> /dev/null'


def error(msg, *args, **kwargs):
    print(msg.format(*args, **kwargs))
    sys.exit(-1)


def expect_file(path):
    if not os.path.exists(path):
        error('Expected file {} to exists', path)


@contextmanager
def open_file(filename, mode):
    if dry_run:
        yield sys.stdout
    else:
        f = open(filename, mode)
        yield f
        f.close()


def print_file(f, value, **kwargs):
    print(value, file=f, **kwargs)


def download(url, filename, retries=10, sleep=6):
    i = 0
    while i < retries:
        try:
            urlretrieve(url, filename)
            return
        except HTTPError:
            info('failed to download {}, will try again in {} seconds', url, sleep)
            i += 1
            time.sleep(sleep)
    error('could now download {}', url)


def ask(question, default):
    return input(question + ' default: \'' + default + '\': ') or default


def is_available(cmd):
    if verbose:
        print('test command: ', cmd)
    return os.system(cmd + ' ' + _to_null) == 0


def debug(msg, *args, **kwargs):
    if verbose:
        print(msg.format(*args, **kwargs))


def info(msg, *args, **kwargs):
    print(msg.format(*args, **kwargs))


def red(text):
    formatted = '\033[31m{text}\033[0m' if os.name != 'nt' else '{text}'
    return formatted.format(text=text)


def green(text):
    formatted = '\033[32m{text}\033[0m' if os.name != 'nt' else '{text}'
    return formatted.format(text=text)


def test(cmd):
    cmd = cmd + ' ' + _to_null
    if verbose:
        print(cmd)
    return os.system(cmd) == 0


def execute(cmd):
    if interactive:
        while True:
            answer = input('Run command: %s\nyes,no,quit: [y/n/q]' % cmd)
            print(answer)
            if answer == 'y':
                break
            elif answer == 'n':
                return
            elif answer == 'q':
                sys.exit(0)
    else:
        if not quiet:
            print(cmd)
    if not dry_run:
        return_value = os.system(cmd)
        if return_value != 0:
            error("%r exit with error code: %s" % (cmd, return_value))


def execute_always(cmd):
    if not quiet:
        print(cmd)
    return_value = os.system(cmd)
    if return_value != 0:
        error("%r exit with error code: %s" % (cmd, return_value))


@contextmanager
def backupped(filename):
    backup = filename + '.backup'
    shutil.copy(filename, backup)
    try:
        yield
    except:
        print("oops, error occurred, restoring backup")
        shutil.copy(backup, filename)
        raise
    finally:
        os.remove(backup)


# TODO: use OrderedDict
packages = []
package_map = {}
package_names = []


class VersionSource(object):

    def __init__(self, package, version_file=None, tuple_variable_name='__version_tuple__'):
        self.package = package
        self.tuple_variable_name = tuple_variable_name
        # if version_file is None:
        self.version_file = version_file or os.path.join(
            self.package.package_path, "_version.py")
        self.version_file = self.version_file.format(**self.package.__dict__)
        self.find_version()
        self.bumped = False

    def find_version(self):
        self.version_module = imp.load_source('version', self.version_file)
        self.version = getattr(self.version_module, self.tuple_variable_name)
        # version_string = self.version_module.__version__
        # semver_string = semver.format_version(*self.version)
        # if semver_string != version_string:
        #     error('semver formats your version as %r, while you format it as %r, please fix this'
        #           % (semver_string, version_string))

    def __str__(self):
        return semver.format_version(*self.version)

    def print(self, indent=0):
        print("\t" * indent + "version: {version}".format(**self.__dict__))
        print("\t" * indent + "file: {version_file}".format(**self.__dict__))

    def bump(self, what):
        if self.bumped:
            debug('version already bumped, don\'t do it twice')
            return
        old = semver.format_version(*self.version)
        types = ['major', 'minor', 'patch', 'prerelease', 'build']
        if what == "last":
            # count how many non None parts there are
            parts = len([k for k in self.version if k is not None])
            new = semver_bump[parts - 1](old)
        elif what in types:
            new = semver_bump[types.index(what)](old)
        else:
            error("unknown what: {}", what)
        info("version was {}, is now {}", old, new)
        self.version = [k for k in semver.parse_version_info(new) if k is not None]
        self.bumped = True


class VersionSourceAndTargetHpp(VersionSource):

    def __init__(self, package, version_file=None, prefix='VERSION_', postfixes=None, patterns=None):
        self.prefix = prefix
        self.postfixes = postfixes or 'MAJOR MINOR PATCH PRERELASE BUILD'.split()
        self.patterns = patterns or ['#DEFINE {prefix}{postfix}'.format(prefix=self.prefix, postfix=postfix).lower()
                                     for postfix in self.postfixes]
        super(VersionSourceAndTargetHpp, self).__init__(package, version_file)

    def find_version(self):
        version = [None] * 5
        with open(self.version_file) as f:
            for line in f.readlines():
                line = line.strip().lower()
                for i, pattern in enumerate(self.patterns):
                    if line.startswith(pattern):
                        value = int(line[len(pattern):])
                        version[i] = value
        # make sure we have major, minor and patch
        for i in range(3):
            if version[i] is None:
                error('Expected to find a {type} version number line starting with: {pattern}',
                      type=self.postfixes[i], pattern=self.patterns[i])
        self.version = [k for k in version if k is not None]

    def save(self):
        newlines = []
        with open(self.version_file) as f:
            for linenr, line in enumerate(f.readlines()):
                newlines.append(line)
                original_line = line
                line = line.strip().lower()
                for i, pattern in enumerate(self.patterns):
                    if line.startswith(pattern):
                        newlines[linenr] = original_line[
                            :len(pattern)] + ' ' + str(self.version[i]) + '\n'

        if not dry_run:
            with backupped(self.version_file):
                with open(self.version_file, 'w') as f:
                    f.write(''.join(newlines))
        else:
            print("would write\n:" + ''.join(newlines))
        info('wrote to {}', self.version_file)
        execute('git commit -m "Release {version}" {files}'.format(
            version=self.version_source, files=self.version_file))

import json
import collections

class VersionTargetJson(object):
    def __init__(self, package, json_file, key='version', indent=2):
        self.package = package
        self.json_file = json_file.format(**self.package.__dict__)
        self.key = key
        self.version_source = None
        self.indent = indent

    def save(self):
        if self.version_source is None:
            error('no version set')
        with open(self.json_file, 'r') as f:
            values = json.JSONDecoder(object_pairs_hook=collections.OrderedDict).decode(f.read())
        value = values
        names = self.key.split('.')
        head = names[-1]
        tail = names[:-1]
        for name in tail:
            value = values[name]
        value[head] = str(self.version_source)
        dump = json.dumps(values, indent=self.indent)
        if not dry_run:
            with backupped(self.json_file):
                with open(self.json_file, 'w') as f:
                    f.write(dump)
        else:
            print("would write:\n" + dump)
        info('wrote to {}', self.json_file)
        execute('git commit -m "Release {version}" {files}'.format(
            version=self.version_source, files=self.json_file))



class VersionTarget(object):

    def __init__(self, package, version_file=None, tuple_variable_name='__version_tuple__', string_variable_name='__version__'):
        self.package = package
        # if version_file is None:
        self.version_file = version_file or os.path.join(
            self.package.package_path, "_version.py")
        self.version_file = self.version_file.format(**self.package.__dict__)
        self.tuple_variable_name = tuple_variable_name
        self.string_variable_name = string_variable_name
        self.validate_file()
        self.version_source = None


    def validate_file(self):
        version_found = False
        version_tuple_found = False
        with open(self.version_file) as f:
            lines = f.readlines()
            for line in lines:
                if re.match(self.string_variable_name + '.*', line):
                    version_found = True
                if re.match(self.tuple_variable_name + '.*', line):
                    version_tuple_found = True
        if not (version_found and version_tuple_found):
            error("did not find " +self.string_variable_name +" and " +self.tuple_variable_name +" in {}", self.version_file)

    def save(self):
        if self.version_source is None:
            error('no version set')
        newlines = []
        with open(self.version_file) as f:
            lines = f.readlines()
            for line in lines:
                if re.match(self.string_variable_name + '.*', line):
                    newlines.append(self.string_variable_name + ' = %r\n' %
                                    str(self.version_source))
                elif re.match(self.tuple_variable_name + '.*', line):
                    newlines.append(self.tuple_variable_name + ' = %r\n' %
                                    (tuple(self.version_source.version),))
                else:
                    newlines.append(line)
        if not dry_run:
            with backupped(self.version_file):
                with open(self.version_file, 'w') as f:
                    f.write(''.join(newlines))
        else:
            print("would write:\n" + ''.join(newlines))
        info('wrote to {}', self.version_file)
        execute('git commit -m "Release {version}" {files}'.format(
            version=self.version_source, files=self.version_file))


class ReleaseTargetGitTagVersion(object):

    def __init__(self, version_source, prefix='v', postfix='', annotate=True, msg='Release {version}'):
        self.version_source = version_source
        self.prefix = prefix
        self.postfix = postfix
        self.tagged = False
        self.annotate = annotate
        self.msg = msg

    def __str__(self):
        return self.prefix + str(self.version_source) + self.postfix

    def py_normalized(self):
        return pkg_resources.safe_version(str(self))

    def exists(self):
        return test('git rev-parse {tag}'.format(tag=str(self)))

    def clean_since(self, path=''):
        version_tag = str(self)
        return test('git diff --exit-code {version_tag}...HEAD {path}'.format(path=path, version_tag=version_tag))

    def do(self, last_package):
        if self.tagged:
            debug('already tagged, don\'t do it twice')
            return
        if self.version_source is None:
            error('no version set for tagging')
        tag = str(self)
        if self.annotate:
            msg = self.msg.format(version=self.version_source)
            cmd = 'git tag -a {tag} -m "{msg}"'.format(tag=tag, msg=msg)
        else:
            cmd = 'git tag %s' % tag
        if force:
            cmd += " -f"
        if dry_run:
            print(cmd)
        else:
            execute(cmd)
        self.tagged = True


class ReleaseTargetSourceDist:

    def __init__(self, package):
        self.package = package

    def do(self, last_package):
        cmd = "cd {path} && python setup.py sdist upload".format(
            **self.package.__dict__)
        execute(cmd)

class ReleaseTargetNpm:

    def __init__(self, package):
        self.package = package

    def do(self, last_package):
        cmd = "cd {path} && npm publish".format(
            **self.package.__dict__)
        execute(cmd)

class ReleaseTargetGitPush:

    def __init__(self, repository='', refspec=''):
        self.repository = repository
        self.refspec = refspec

    def do(self, last_package):
        if not last_package:
            return
        if force:
            cmd = "git push {repository} {refspec} --force && git push {repository} --tags --force"
        else:
            cmd = "git push {repository} {refspec} && git push {repository} --tags"
        execute(cmd.format(repository=self.repository, refspec=self.refspec))


def replace_in_file(filename, *replacements):
    newlines = []
    found = [False] * len(replacements)
    with open(filename) as f:
        lines = f.readlines()
        for line in lines:
            replacement_done = False
            for i, (regex, replacement) in enumerate(replacements):
                if re.match(regex, line):
                    if found[i]:
                        error('{} -> {} found multiple files in file {}',
                              regex, replacement, filename)
                    if replacement[-1] != '\n':
                        replacement += '\n'
                    newlines.append(replacement)
                    found[i] = True
                    replacement_done = True
            if not replacement_done:
                newlines.append(line)
    for i, (regex, replacement) in enumerate(replacements):
        if not found[i]:
            error('{} -> {} not found in file {}',
                  regex, replacement, filename)

    content = ''.join(newlines)
    if not dry_run:
        with backupped(filename):
            with open(filename, 'w') as f:
                f.write(content)
    else:
        info('would write: \n{}', content)
    print('updating', filename)


class ReleaseTargetCondaForge:

    def __init__(self, package, feedstock_path, source_tarball_filename=None):
        self.package = package
        self.feedstock_path = feedstock_path
        self.branch = 'update_to_' + str(self.package.version_source)
        self.source_tarball_filename = source_tarball_filename

    def do(self, last_package):
        source_tarball_filename = self.source_tarball_filename
        version = str(self.package.version_source)
        if self.source_tarball_filename is None:
            # this is what setuptools does
            version_unnormalized = str(self.package.version_source)
            version_normalized = pkg_resources.safe_version(
                version_unnormalized)
            version = version_normalized
            debug('normalized version from {} to {}',
                  version_unnormalized, version_normalized)
            source_tarball_filename = os.path.join(self.package.path, 'dist', self.package.distribution_name +
                         '-' + version_normalized + '.tar.gz')

        if source_tarball_filename.startswith('http'):
            fileno, filename = tempfile.mkstemp()
            info('will download {} to {}',
                  self.source_tarball_filename, filename)
            download(self.source_tarball_filename, filename)
            source_tarball_filename = filename

        expect_file(source_tarball_filename)
        with open(source_tarball_filename, 'rb') as f:
            hash_sha256 = hashlib.sha256(f.read()).hexdigest()

        # put repo in a good state
        cmd = "cd {feedstock_path} && git stash && git checkout master &&  git pull upstream master".format(
            **self.__dict__)
        execute(cmd)

        cmd = "cd {feedstock_path} && git checkout -b {branch}".format(
            **self.__dict__)
        execute(cmd)

        debug('sha256 = {}', hash_sha256)

        filename = os.path.join(self.feedstock_path, 'recipe', 'meta.yaml')
        replace_in_file(filename,
                        ('  number:.*', '  number: 0'),
                        ('{% set version =', '{%% set version = "%s" %%}' % version),
                        ('{% set sha256 =', '{%% set sha256 = "%s" %%}' % hash_sha256))

        cmd = 'cd {feedstock_path} && git commit -am "Update to version {version}"'.format(
            version=version, **self.__dict__)
        execute(cmd)

        cmd = 'cd {feedstock_path} && git push origin {branch}'.format(
            **self.__dict__)
        execute(cmd)

        cmd = 'cd {feedstock_path} && hub pull-request -m "Update to version {version}"'.format(
            version=version, **self.__dict__)

        if is_available('hub --help'):
            execute(cmd)
        else:
            print("*** the command line tool 'hub' is not aviable, so could not execute:")
            print(cmd)
            print('*** please do the pull request manually')


class Package:

    def __init__(self, path, name, distribution_name=None, package_name=None, version_source=None, version_targets=None, filenames=None):
        self.path = path
        self.abspath = os.path.abspath(path)
        self.name = name
        self.distribution_name = distribution_name or name
        self.package_name = package_name
        self.package_path = None
        if package_name is not None:
            self.package_path = os.path.join(
                self.path, *package_name.split("."))
        self.version_source = None  # version_source or VersionSource(self)
        self.version_targets = version_targets or []
        self.release_targets = []
        self.filenames = filenames # files to track to see if dirty

    def print(self, indent=0):
        print("\t" * indent + "name: {name}".format(**self.__dict__))
        print("\t" * indent + "path: {path}".format(**self.__dict__))
        print("\t" * indent +
              "package_name: {package_name}".format(**self.__dict__))
        print("\t" * indent + "version: ")
        self.version_source.print(indent=indent + 1)

    def release(self, last_package):
        for release_target in self.release_targets:
            release_target.do(last_package=last_package)

    def get_tag_target(self):
        # this should move as well, too git specific
        tag = [k for k in self.release_targets if isinstance(
            k, ReleaseTargetGitTagVersion)]
        assert len(tag) == 1, "no tag target set"
        return tag[0]

    def is_clean(self):
        if self.filenames:
            return test('git diff --exit-code ' + ' '.join(self.filenames))
        else:
            return test('git diff --exit-code {path}'.format(**self.__dict__))

    def count_untracked_files(self):
        cmd = 'git ls-files --other --exclude-standard --directory {path}'.format(
            path=self.path)
        result = os.popen(cmd).read()
        # count non empty lines
        return len([k for k in result.split('\n') if k.strip()])

    def print_status(self):
        clean = self.is_clean()
        status = ''
        if clean:
            status += '\t' + green('clean                 ')
        else:
            status += '\t' + red('dirty (commit changes)')
        tag = self.get_tag_target()
        if tag.exists():
            clean = tag.clean_since(path=self.path)
            if clean:
                status += '|' + green('everything up to date           ')
            else:
                status += '|' + red('version bump needed & release   ')
        else:
            status += '|' + red('version not tagged, run release?')
        untracked = self.count_untracked_files()
        if untracked:
            status += '|' + red('%d untracked files' % untracked)
        print('{name}:\t{status}'.format(status=status, **self.__dict__))
        if verbose:
            print('Untracked files:')
            cmd = 'git ls-files --other --exclude-standard --directory {path}'.format(
                path=self.path)
            execute_always(cmd)

    def bump(self, what):
        # this is git specific, move this out
        if not self.is_clean():
            msg = 'package {name} (dir: {path}) dirty, commit changes first'.format(
                **self.__dict__)
            if force:
                print(msg)
            else:
                error(msg)
        self.version_source.bump(what)

    def set(self):
        for target in self.version_targets:
            target.version_source = self.version_source
        for target in self.version_targets:
            target.save()


def add_package(path, name=None, package_name=None, distribution_name=None, version_source=None, filenames=None):
    name = name or os.path.split(path)[-1]
    package_name = package_name or name
    package = Package(path, name, distribution_name=distribution_name, package_name=package_name, version_source=version_source, filenames=filenames)
    packages.append(package)
    package_names.append(name)
    package_map[name] = package
    return package


def cmd_list(args):
    print("packages:")
    for package in packages:
        print("\t- package")
        package.print(indent=2)


def package_iter(package_names):
    for i, package_name in enumerate(package_names):
        if package_name not in package_map:
            error("no package called %s, known package(s): %s" %
                  (package_name, ", ".join([repr(k.name) for k in packages])))
        package = package_map[package_name]
        yield package, i == len(package_names) - 1


def main(argv=sys.argv):
    import argparse
    global dry_run, force, verbose, quiet, interactive
    parser = argparse.ArgumentParser(argv[0])

    subparsers = parser.add_subparsers(help='type of command', dest="task")

    parser_status = subparsers.add_parser('status', help='list packages\' status')
    subparsers.add_parser('list', help='list packages')
    parser_set = subparsers.add_parser('set', help='set versions')
    parser_bump = subparsers.add_parser('bump', help='bump version nr')
    parser_release = subparsers.add_parser('release', help='release software')
    parser_conda_forge_init = subparsers.add_parser('conda-forge-init', help='make a conda-forge recipe')

    parser_status.add_argument('packages', help="which packages", nargs="*")

    action_subparsers = [parser_bump, parser_release,
                         parser_set, parser_conda_forge_init]
    for subparser in action_subparsers:
        subparser.add_argument('--dry-run', '-n', action='store_true',
                               default=False, help="do not execute, but print")
        subparser.add_argument('--force', '-f', action='store_true',
                               default=False, help="force actions (such as tagging)")
        subparser.add_argument('--interactive', '-i', action='store_true',
                               default=False, help="ask for confirmation before running")
    for subparser in action_subparsers + [parser_status]:
        subparser.add_argument('--verbose', '-v', action='store_true', default=False, help="more output")
        subparser.add_argument('--quiet', '-q', action='store_true', default=False, help="less output")

    parser_bump.add_argument('--all', '-a', action='store_true', default=False, help="all packages")
    parser_bump.add_argument('packages', help="which packages", nargs="*")
    parser_bump.add_argument('--what', '-w', help="which packages", default='last')

    parser_release.add_argument('packages', help="which packages", nargs="*")

    parser_set.add_argument('packages', help="which packages", nargs="*")

    parser_conda_forge_init.add_argument('packages', help="which packages", nargs="*")
    parser_conda_forge_init.add_argument('--repo', '-w', help="forked repo for staged-recipes", default=None)

    args = parser.parse_args(argv[1:])

    imp.load_source('releash-config', '.releash.py')

    if hasattr(args, 'dry_run'):
        dry_run = args.dry_run
    if hasattr(args, 'force'):
        force = args.force
    if hasattr(args, 'interactive'):
        interactive = args.interactive
    verbose = args.verbose
    quiet = args.quiet
    if args.task == "list":
        cmd_list(args)
    elif args.task == "status":
        for package, last in package_iter(args.packages or package_names):
            package.print_status()
    elif args.task == "bump":
        for package, last in package_iter(args.packages or package_names):
            package.bump(args.what)
            package.set()
    elif args.task == "set":
        for package, last in package_iter(args.packages or package_names):
            package.set()
    elif args.task == "release":
        for package, last in package_iter(args.packages or package_names):
            package.release(last)
    elif args.task == "conda-forge-init":
        if args.repo is None:
            error("please provide --repo")
        if not os.path.exists(args.repo):
            error("path to repo not found: {}", args.repo)
        cmd = "cd {repo_path} && git stash && git checkout master &&  git pull upstream master".format(
            repo_path=args.repo)
        execute(cmd)
        for package, last in package_iter(args.packages or package_names):
            # source_dists = [k for k in package.release_targets if isinstance(ReleaseTargetSourceDist)]
            # source_dist = source_dists[0] of len(source_dists) == 1 else None

            version_unnormalized = str(package.version_source)
            # this is what setuptools does
            version_normalized = pkg_resources.safe_version(
                version_unnormalized)

            source_tarball_filename = os.path.join(
                package.path, 'dist', package.name + '-' + version_normalized + '.tar.gz')
            expect_file(source_tarball_filename)
            with open(source_tarball_filename, 'rb') as f:
                hash_sha256 = hashlib.sha256(f.read()).hexdigest()
            print("for", package.name)
            format_kwargs = dict(repo_path=args.repo, name=package.name, version=version_normalized,
                                 path=package.path,
                                 package_name=package.package_name,
                                 nameu=package.name.replace(
                                     '-', '_'),  # TODOl use pkg_utils?
                                 hash=hash_sha256)
            cmd = "cd {repo_path} && git checkout -B {name}".format(
                **format_kwargs)
            execute(cmd)
            # cmd = "cd {repo_path}/recipes && conda skeleton pypi {name} --version={version}".format(**format_kwargs)
            # execute(cmd)
            cmd = "cd {repo_path}/recipes && mkdir -p {name}".format(
                **format_kwargs)
            execute(cmd)

            cmd = "cd {path} && python setup.py egg_info".format(
                **format_kwargs)
            execute(cmd)
            print(format_kwargs)
            with open('{path}/{nameu}.egg-info/requires.txt'.format(**format_kwargs)) as f:
                requires = [k.strip() for k in f.readlines()]

            format_kwargs_feedstock = dict(format_kwargs)
            with open('{path}/{nameu}.egg-info/PKG-INFO'.format(**format_kwargs)) as f:
                for line in f.readlines():
                    line = line.strip()
                    if line:
                        key, value = line.split(":", 1)
                        format_kwargs_feedstock[key.strip()] = value.strip()
            # print(, end='')

            format_kwargs_feedstock['maintainer'] = ask(
                'What is your github username (for maintainer entry)? ', os.environ['USER'])

            with open_file('{repo_path}/recipes/{name}/meta.yaml'.format(**format_kwargs), 'w') as f:
                print_file(f, '''{{% set name = "{name}" %}}
{{% set version = "{version}" %}}
{{% set sha256 = "{hash}" %}}
'''.format(**format_kwargs_feedstock))
                print_file(f, '''package:
  name: {{ name|lower }}
  version: {{ version }}

source:
  fn: {{ name }}-{{ version }}.tar.gz
  url: https://pypi.io/packages/source/{{ name[0] }}/{{ name }}/{{ name }}-{{ version }}.tar.gz
  sha256: {{ sha256 }}

build:
  number: 0
  noarch: python''')
                if os.path.exists('{path}/{nameu}.egg-info/entry_points.txt'.format(**format_kwargs)):
                    print_file(f, '  preserve_egg_dir: True')
                print_file(f, '''  script: python setup.py install --single-version-externally-managed --record record.txt

requirements:
  build:
    - python
    - setuptools
  run:
    - python''')

                for require in requires:
                    # try to put a space in front of the version requirement
                    try:
                        require = re.sub('(.*?)([>=<]+)', r'\1 \2', require)
                    except:
                        pass
                    print_file(f, '    - ' + require)
                print_file(f, '''
test:
  imports:
    - {package_name}

about:
  home: {Home-page}
  license: {License}
  license_family: {License}'''.format(**format_kwargs_feedstock));
                for license_name in 'LICENSE LICENSE.txt'.split():
                    license_path = os.path.join(package.path, license_name)
                    print(license_path)
                    if os.path.exists(license_path):
                        print_file(f, '  license_file: {license_name}'.format(license_name=license_name))
                print_file(f, '''  summary: {Summary}
  description: |
    {Description}

extra:
  recipe-maintainers:
    - {maintainer}'''.format(**format_kwargs_feedstock))

            print('Please check {repo_path}/recipes/{name}/meta.yaml, if you are done, type enter for making a pull request'.format(
                **format_kwargs), end='')
            input('[OK]')

            cmd = 'cd {repo_path} && git add recipes/{name}/* && git commit -am "{name} added"'.format(
                **format_kwargs)
            execute(cmd)

            cmd = 'cd {repo_path} && git push origin {name}'.format(
                **format_kwargs)
            execute(cmd)
            cmd = 'cd {repo_path} && hub pull-request -m "Adding {name} (Generated by releash)"'.format(
                **format_kwargs)
            execute(cmd)


if __name__ == "__main__":
    main()
