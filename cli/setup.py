#!/usr/bin/env python3
"""
AgentOS CLI Setup Script

Install with: pip install -e cli/
"""

from setuptools import setup, find_packages
from pathlib import Path

# Read requirements
requirements_file = Path(__file__).parent / "requirements.txt"
if requirements_file.exists():
    requirements = requirements_file.read_text().strip().split('\n')
    requirements = [r.strip() for r in requirements if r.strip() and not r.startswith('#')]
else:
    requirements = [
        'click>=8.0',
        'pyyaml>=6.0',
        'aiohttp>=3.8',
        'rich>=13.0',
    ]

setup(
    name='agentos-cli',
    version='0.1.0',
    description='AgentOS CLI - Deploy and manage AgentOS kernels anywhere',
    author='AgentOS Team',
    author_email='team@agentos.dev',
    url='https://github.com/agentos-project/agentos',
    packages=find_packages(),
    include_package_data=True,
    install_requires=requirements,
    entry_points={
        'console_scripts': [
            'agentos=agentos:main',
        ],
    },
    python_requires='>=3.8',
    classifiers=[
        'Development Status :: 3 - Alpha',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: MIT License',
        'Programming Language :: Python :: 3',
        'Programming Language :: Python :: 3.8',
        'Programming Language :: Python :: 3.9',
        'Programming Language :: Python :: 3.10',
        'Programming Language :: Python :: 3.11',
    ],
)
