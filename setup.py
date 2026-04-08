from setuptools import find_packages, setup


setup(
    name="pm-method-agent",
    version="0.1.0",
    description="面向问题定义质量的产品分析方法智能体",
    package_dir={"": "src"},
    packages=find_packages("src"),
    python_requires=">=3.9",
    entry_points={
        "console_scripts": [
            "pm-method-agent=pm_method_agent.cli:main",
        ]
    },
)
