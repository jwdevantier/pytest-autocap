import os
from setuptools import setup
from pathlib import Path


PKG_ROOT = Path(__file__).parent


def get_requirements():
    # intentionally naive, does not support include files etc
    with open("./requirements.txt") as fp:
        return fp.read().split()


README = (PKG_ROOT / "README.md").read_text()


version = os.getenv("GITHUB_REF", "refs/tags/0.0.1").split("/")[-1]
print(f"Building version: {version}")

setup(
    name="pytest-autocap",
    description="automatically capture test & fixture stdout/stderr to files",
    long_description=README,
    long_description_content_type="text/markdown",
    classifiers=["Framework :: Pytest"],
    version=version,
    author="Jesper Wendel Devantier",
    author_email="jwd@defmacro.it",
    url="https://github.com/jwdevantier/pytest-autocap",
    packages=["pytest_autocap"],
    install_requires=get_requirements(),
    entry_points={
        "pytest11": [
            "pytest_autocap = pytest_autocap.pluginmodule",
        ],
    },
    license="MIT",
    options={"bdist_wheel": {"universal": True}},
)
