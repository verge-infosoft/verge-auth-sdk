from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension(
        "verge_auth_sdk.middleware",
        sources=["verge_auth_sdk/middleware.py"],
    ),
    Extension(
        "verge_auth_sdk.secret_provider",
        sources=["verge_auth_sdk/secret_provider.py"],
    ),
    Extension(
        "verge_auth_sdk.verge_routes",
        sources=["verge_auth_sdk/verge_routes.py"],
    ),
]

setup(
    name="verge-auth-sdk",
    version="0.1.5",
    packages=["verge_auth_sdk"],
    ext_modules=cythonize(
        extensions,
        compiler_directives={"language_level": "3"},
        annotate=False
    ),
    include_package_data=True,
)
