#!/bin/bash

echo "Cleaning previous builds..."
rm -rf build dist *.egg-info
rm -rf verge_auth_sdk/*.c verge_auth_sdk/*.so verge_auth_sdk/*.pyd

echo "Installing build deps..."
pip install --upgrade pip build

echo "Building wheel and sdist..."
python -m build

echo "DONE. Wheels in dist/:"
ls dist
