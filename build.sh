#!/bin/bash

echo "Cleaning build folders..."
rm -rf build dist verge_auth_sdk/*.c verge_auth_sdk/*.pyd

echo "Installing build deps..."
pip install --upgrade pip setuptools wheel build cython

echo "Building wheel..."
python setup.py bdist_wheel

echo "DONE. Wheels in dist/"
ls dist
