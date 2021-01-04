import buildbot_fossil
import pathlib
from setuptools import setup, find_packages

here = pathlib.Path(__file__).parent.resolve()
long_description = (here / 'README.md').read_text(encoding='utf-8')

setup(
    name='buildbot-fossil',
    version=buildbot_fossil.__version__,
    description='Fossil version control plugin for Buildbot',
    long_description=long_description,
    long_description_content_type='text/markdown',
    url='https://github.com/stoklund/buildbot-fossil',
    author='Jakob Stoklund Olesen',
    author_email='stoklund@2pi.dk',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'Topic :: Software Development :: Build Tools',
        'Topic :: Software Development :: Testing',
        'License :: OSI Approved :: GNU General Public License v2 (GPLv2)',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.5',
        'Programming Language :: Python :: 3.6',
        'Programming Language :: Python :: 3.7',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3 :: Only',
    ],
    keywords='Buildbot, Fossil SCM',
    packages=find_packages(),
    python_requires='>=3.5, <4',
    install_requires=['buildbot', 'treq'],
    entry_points={
        'buildbot.changes': [
            'FossilPoller = buildbot_fossil.changes:FossilPoller',
        ],
        'buildbot.steps': [
            'Fossil = buildbot_fossil.steps:Fossil',
        ],
    },
    project_urls={
        'Bug Reports': 'https://github.com/stoklund/buildbot-fossil/issues',
        'Documentation': 'https://buildbot-fossil.readthedocs.io/',
    },
)
