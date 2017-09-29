#!/usr/bin/env python
import sys, os, imp, re
import shutil
from contextlib import contextmanager

import semver

__version_tuple__ = (0, 1, 0, 'alpha.3', None)
__version__ = '0.1.0-alpha.3'

semver_bump = [semver.bump_major, semver.bump_minor, semver.bump_patch, semver.bump_prerelease, semver.bump_build]
def error(msg, *args, **kwargs):
    print(msg.format(*args, **kwargs))
    sys.exit(-1)

def expect_file(path):
    if not os.path.exists(path):
        error('Expected file {} to exists', path)
def is_available(cmd):
    return os.system('hub --help > /dev/null') == 0

def debug(msg, *args, **kwargs):
    print(msg.format(*args, **kwargs))
def execute(cmd):
    print(cmd)
    return_value = os.system(cmd)
    if return_value != 0:
        error("%r exit with error code: %s" % (cmd, return_value))

@contextmanager
def backupped(filename):
    backup = filename+'.backup'
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
    def __init__(self, package, version_file=None):
        self.package = package
        #if version_file is None:
        self.version_file = version_file or os.path.join(self.package.package_path, "_version.py")
        self.find_version()

    def find_version(self):
        self.version_module = imp.load_source('version', self.version_file)
        self.version = self.version_module.__version_tuple__
        version_string = self.version_module.__version__
        semver_string = semver.format_version(*self.version)
        if semver_string != version_string:
            error('semver formats your version as %r, while you format it as %r, please fix this'
                % (semver_string, version_string))

    def __str__(self):
        return semver.format_version(*self.version)

    def print(self, indent=0):
        print("\t" * indent + "version: {version}".format(**self.__dict__))
        print("\t" * indent + "file: {version_file}".format(**self.__dict__))

    def bump(self, what, dryrun=False, force=False):
        old_version = self.version
        old = semver.format_version(*self.version)
        if what == "last":
            # count how many non None parts there are
            parts = len([k for k in self.version if k is not None])
            new = semver_bump[parts-1](old)
        else:
            error("unknown what: {}", what)
        debug("version was {}, is now {}", old, new)
        self.version = semver.parse_version_info(new)

class VersionTarget(object):
    def __init__(self, package, version_file=None):
        self.package = package
        #if version_file is None:
        self.version_file = version_file or os.path.join(self.package.package_path, "_version.py")
        self.validate_file()
        self.version_source = None

    def validate_file(self):
        version_found = False
        version_tuple_found = False
        with open(self.version_file) as f:
            lines = f.readlines()
            for line in lines:
                if re.match('__version__.*', line):
                    version_found = True
                if re.match('__version_tuple__.*', line):
                    version_tuple_found = True

    def save(self, dryrun=False, force=False):
        if self.version_source is None:
            error('no version set')
        newlines = []
        with open(self.version_file) as f:
            lines = f.readlines()
            for line in lines:
                if re.match('__version__.*', line):
                    newlines.append('__version__ = %r\n' % str(self.version_source))
                elif re.match('__version_tuple__.*', line):
                    newlines.append('__version_tuple__ = %r\n' % (tuple(self.version_source.version),))
                else:
                    newlines.append(line)
        if not dryrun:
            with backupped(self.version_file):
                with open(self.version_file, 'w') as f:
                    f.write(''.join(newlines))
        debug('wrote to {}', self.version_file)

class VersionTargetGitTag(object):
    def __init__(self, prefix='v', postfix=''):
        self.prefix = prefix
        self.postfix = postfix
        self.version_source = None

    def save(self, dryrun=False, force=False):
        if self.version_source is None:
            error('no version set')
        cmd = "git tag %s" % str(self.version_source)
        if force:
            cmd += " -f"
        if dryrun:
            print(cmd)
        else:
            execute(cmd)


class ReleaseTargetSourceDist:
    def __init__(self, package):
        self.package = package

    def release(self, force=False, dryrun=False):
        cmd = "cd {path}; python setup.py sdist upload".format(**self.package.__dict__)
        if dryrun:
            print(cmd)
        else:
            execute(cmd)

class ReleaseTargetGitPush:
    def __init__(self, package):
        self.package = package

    def release(self, force=False, dryrun=False):
        if force:
            cmd = "git push --force && git push --tags --force"
        else:
            cmd = "git push && git push --tags"
        if dryrun:
            print(cmd)
        else:
            execute(cmd)

def replace_in_file(filename, *replacements, dryrun=False):
    newlines = []
    found = [False] * len(replacements)
    with open(filename) as f:
        lines = f.readlines()
        for line in lines:
            replacement_done = False
            for i, (regex, replacement) in enumerate(replacements):
                if re.match(regex, line):
                    if found[i]:
                        error('{} -> {} found multiple files in file {}', regex, replacement, filename)
                    if replacement[-1] != '\n':
                        replacement += '\n'
                    newlines.append(replacement)
                    found[i] = True
                    replacement_done = True
            if not replacement_done:
                newlines.append(line)
    for i, (regex, replacement) in enumerate(replacements):
        if not found[i]:
            error('{} -> {} not found in file {}', regex, replacement, filename)

    content = ''.join(newlines)
    if not dryrun:
        with backupped(filename):
            with open(filename, 'w') as f:
                f.write(content)
    else:
        debug('would write: \n{}', content)
    print('updating', filename)

class ReleaseTargetCondaForge:
    def __init__(self, package, feedstock_path, source_tarball_filename=None):
        self.package = package
        self.feedstock_path = feedstock_path
        self.branch = 'update_to_' + str(self.package.version_source)
        self.source_tarball_filename = source_tarball_filename

    def release(self, force=False, dryrun=False):
        import pkg_resources
        import hashlib
        version_unnormalized = str(self.package.version_source)
        # this is what setuptools does
        version_normalized = pkg_resources.safe_version(version_unnormalized)
        debug('normalized version from {} to {}', version_unnormalized, version_normalized)
        source_tarball_filename = self.source_tarball_filename or \
            os.path.join(self.package.path, 'dist', self.package.name + '-' + version_normalized + '.tar.gz')
        expect_file(source_tarball_filename)
        with open(source_tarball_filename, 'rb') as f:
            hash_sha256 = hashlib.sha256().hexdigest()

        # put repo in a good state
        cmd = "cd {feedstock_path}; git stash && git checkout master &&  git pull upstream master".format(**self.__dict__)
        if dryrun:
            print(cmd)
        else:
            execute(cmd)

        cmd = "cd {feedstock_path} && git checkout -b {branch}".format(**self.__dict__)
        if dryrun:
            print(cmd)
        else:
            execute(cmd)
        filename = os.path.join(self.feedstock_path, 'recipe', 'meta.yaml')
        replace_in_file(filename, 
            ('{% set version =', '{%% set version = "%s" %%}' % version_normalized),
            ('{% set sha256 =', '{%% set sha256 = "%s" %%}' % hash_sha256),
            dryrun=dryrun)

        cmd = "cd {feedstock_path}; git commit -am 'Update to version {version}'".format(version=str(self.package.version_source), **self.__dict__)
        if dryrun:
            print(cmd)
        else:
            execute(cmd)

        cmd = "cd {feedstock_path}; git push origin {branch}".format(**self.__dict__)
        if dryrun:
            print(cmd)
        else:
            execute(cmd)

        cmd = "cd {feedstock_path}; hub pull-request -m 'Update to version {version}'".format(version=str(self.package.version_source), **self.__dict__)

        if is_available('hub --help'):
            if dryrun:
                print(cmd)
            else:
                execute(cmd)
        else:
            print("*** the command line tool 'hub' is not aviable, so could not execute:")
            print(cmd)
            print('*** please do the pull request manually')

class Package:
    def __init__(self, path, name, package_name=None, version_source=None, version_targets=None):
        self.path = path
        self.abspath = os.path.abspath(path)
        self.name = name
        self.package_name = package_name
        self.package_path = None
        if package_name is not None:
            self.package_path = os.path.join(self.path, *package_name.split("."))
        self.version_source = None#version_source or VersionSource(self)
        self.version_targets = version_targets or []
        self.release_targets = []

    def print(self, indent=0):
        print("\t" * indent + "name: {name}".format(**self.__dict__))
        print("\t" * indent + "path: {path}".format(**self.__dict__))
        print("\t" * indent + "package_name: {package_name}".format(**self.__dict__))
        print("\t" * indent + "version: ")
        self.version_source.print(indent=indent+1)

    def release(self, dryrun=False, force=False):
        for release_target in self.release_targets:
            release_target.release(dryrun=dryrun, force=force)

    def bump(self, what, dryrun=False, force=False):
        self.version_source.bump(what)
        for target in self.version_targets:
            target.version_source = self.version_source
        for target in self.version_targets:
            target.save(dryrun=dryrun, force=force)

def add_package(path, name=None, package_name=None, version_source=None):
    name = name or os.path.split(path)[-1]
    package_name = package_name or name
    package = Package(path, name, package_name, version_source=version_source)
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
    for package_name in package_names:
        if package_name not in package_map:
            error("no package called %s, known package(s): %s" % (package_name, ", ".join([repr(k.name) for k in packages])))
        package = package_map[package_name]
        yield package
def main(argv=sys.argv):
    import argparse
    parser = argparse.ArgumentParser(argv[0])

    subparsers = parser.add_subparsers(help='type of command', dest="task")

    parser_list = subparsers.add_parser('list', help='list packages')
    parser_set = subparsers.add_parser('set', help='set versions')
    parser_bump = subparsers.add_parser('bump', help='bump version nr')
    parser_release = subparsers.add_parser('release', help='release software')

    parser_bump.add_argument('--all','-a', action='store_true', default=False, help="all packages")
    parser_bump.add_argument('packages', help="which packages", nargs="*")
    parser_bump.add_argument('--what', '-w', help="which packages", default='last')
    parser_bump.add_argument('--dry-run', '-n', action='store_true', default=False, help="do not execute, but print")
    parser_bump.add_argument('--force', '-f', action='store_true', default=False, help="force actions (such as tagging)")

    parser_release.add_argument('packages', help="which packages", nargs="*")
    parser_release.add_argument('--dry-run', '-n', action='store_true', default=False, help="do not execute, but print")
    parser_release.add_argument('--force', '-f', action='store_true', default=False, help="force actions (such as tagging)")

    parser_set.add_argument('packages', help="which packages", nargs="*")
    parser_set.add_argument('--dry-run', '-n', action='store_true', default=False, help="do not execute, but print")
    parser_set.add_argument('--force', '-f', action='store_true', default=False, help="force actions (such as tagging)")


    args = parser.parse_args(argv[1:])

    config = imp.load_source('releash-config', '.releash.py')

    if args.task == "list":
        cmd_list(args)
    elif args.task == "bump":
        for package in package_iter(args.packages or package_names):
            package.bump(args.what, dryrun=args.dry_run, force=args.force)
    elif args.task == "set":
        for package in package_iter(args.packages or package_names):
            for target in package.version_targets:
                target.version_source = package.version_source
                target.save(dryrun=args.dry_run, force=args.force)
    elif args.task == "release":
        for package in package_iter(args.packages or package_names):
            package.release(dryrun=args.dry_run, force=args.force)


if __name__ == "__main__":
    main()