from setuptools import setup, find_packages

setup(
    name="verge_auth_sdk",
    version="0.0.13",
    packages=find_packages(),
    install_requires=[
        "fastapi",
        "httpx",
        "python-dotenv",
    ],
)
