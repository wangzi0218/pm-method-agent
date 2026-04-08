from setuptools import find_packages, setup


setup(
    name="pm-method-agent",
    version="0.1.0",
    description="A method-layer agent for improving product problem definition quality.",
    author="wangzi0218",
    python_requires=">=3.9",
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    entry_points={
        "console_scripts": [
            "pm-method-agent=pm_method_agent.cli:main",
        ]
    },
)
