from Cython.Build import cythonize
from setuptools import setup, Extension
import os

package = "verge_auth_sdk"

extensions = []
for root, dirs, files in os.walk(package):
    for file in files:
        if file.endswith(".py") and not file.startswith("__"):
            full = os.path.join(root, file)
            mod = full.replace("/", ".").replace("\\", ".")[:-3]
            extensions.append(Extension(mod, [full]))

setup(
    ext_modules=cythonize(
        extensions,
        compiler_directives={
            "language_level": "3",
            "embedsignature": False,
            "binding": False,
        }
    )
)
