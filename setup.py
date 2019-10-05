from pathlib import Path
from setuptools import setup, find_packages

setup(
    name='evtx2es',
    version="1.0.0",
    author='s.nakano',
    author_email='j15322sn@gmail.com',
    license='MIT',
    packages=find_packages('src', exclude=()),
    package_dir={
        'evtx2es': 'src'
    },
    install_requires=[require for require in Path(Path(__file__).parent, 'requirements.txt').read_text().splitlines()],
    entry_points={
        "console_scripts": [
            "evtx2es = evtx2es.evtx2es:main"
        ]
    }
)