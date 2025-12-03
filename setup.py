from setuptools import setup, Extension, find_packages
from Cython.Build import cythonize

extensions = [
    Extension("verge_auth_sdk.secret_provider", [
              "verge_auth_sdk/secret_provider.py"]),
    Extension("verge_auth_sdk.verge_routes", [
              "verge_auth_sdk/verge_routes.py"]),
    Extension("verge_auth_sdk.middleware", ["verge_auth_sdk/middleware.py"]),
]

setup(
    name="verge_auth_sdk",
    version="0.1.4",
    packages=find_packages(),
    ext_modules=cythonize(extensions, compiler_directives={
                          "language_level": "3"}),
    include_package_data=True,
    zip_safe=False,
    package_data={
        "verge_auth_sdk": ["*.pyd"],
    },
    exclude_package_data={
        "verge_auth_sdk": ["*.py"],
    },

)
