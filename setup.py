import os, imp
from setuptools import setup

dirname = os.path.dirname(__file__)
releash_path = os.path.join(dirname, "releash.py")
version = imp.load_source('releash', releash_path).__version__


setup(
    name='releash',
    version=version,
    description='Release with relish to PyPi and conda-forge, version bumping, pure bliss!',
    url='https://github.com/maartenbreddels/releash',
    author='Maarten A. Breddels',
    author_email='maartenbreddels@gmail.com',
    install_requires=[],
    license='MIT',
    py_modules=['releash'],
    entry_points = {
        'console_scripts': ['releash=releash:main'],
    }
)