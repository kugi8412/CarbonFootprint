# Publishing `carbon-footprint-tracker` to PyPI

The package is pure Python (one `py3-none-any` wheel for every OS) and
targets Python 3.9+. The C++ application is shipped in the source
distribution only; `pip` never compiles it.

## 1. Set the version

The version lives in one place: `carbon_tracker/_version.py`.
`pyproject.toml` and the C++ build (`CMakeLists.txt`) both read it.
PyPI never accepts the same version twice, so bump it for every upload.

## 2. Test

```bash
pip install -e ".[dev,gui]"
pytest                      # GUI tests run headless; without PyQt5 they are skipped
```

The tests never use the network or real power sensors, so they give the
same result on any machine (Windows, Linux, macOS, CI).

## 3. Build

```bash
pip install build twine
python -m build             # -> dist/carbon_footprint_tracker-X.Y.Z.tar.gz + ...-py3-none-any.whl
twine check --strict dist/*
```

Build from a clean checkout: `python -m build` copies whatever is in the
tree into the sdist according to `MANIFEST.in`.

## 4. Try the wheel in a fresh environment

```bash
python -m venv /tmp/cft && /tmp/cft/bin/pip install dist/*.whl
/tmp/cft/bin/carbon-tracker --version
/tmp/cft/bin/carbon-tracker detect
```

(Windows: `py -m venv %TEMP%\cft` and `%TEMP%\cft\Scripts\carbon-tracker`.)

## 5. Upload

Create an API token at <https://pypi.org/manage/account/token/> (user name
`__token__`, password = the token), then upload to TestPyPI first:

```bash
twine upload --repository testpypi dist/*
pip install -i https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple/ carbon-footprint-tracker
```

and, when that install works, to PyPI:

```bash
twine upload dist/*
```

After the upload `pip install carbon-footprint-tracker` (and
`pip install "carbon-footprint-tracker[gui]"` for the desktop GUI) works
everywhere.
