import os, re
from setuptools import setup

dirname = os.path.dirname(__file__)
releash_path = os.path.join(dirname, "releash.py")
with open(releash_path) as f:
    version_match = re.search(r"^__version__ = ['\"]([^'\"]*)['\"]",
                              f.read(), re.M)
version = version_match.group(1)

setup(
    name='releash',
    version=version,
    description='Release with relish to PyPi and conda-forge, version bumping, pure bliss!',
    url='https://github.com/maartenbreddels/releash',
    author='Maarten A. Breddels',
    author_email='maartenbreddels@gmail.com',
    install_requires=['semver'],
    license='MIT',
    py_modules=['releash'],
    entry_points = {
        'console_scripts': ['releash=releash:main'],
    }
)