from setuptools import setup, Extension
from Cython.Build import cythonize

extensions = [
    Extension("verge_auth_sdk.middleware", ["verge_auth_sdk/middleware.py"]),
    Extension("verge_auth_sdk.secret_provider", ["verge_auth_sdk/secret_provider.py"]),
    Extension("verge_auth_sdk.verge_routes", ["verge_auth_sdk/verge_routes.py"]),
]

setup(
    ext_modules=cythonize(
        extensions,
        compiler_directives={"language_level": "3"},
        annotate=False,
    )
)
