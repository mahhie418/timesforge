import os
import pathlib
import tomllib

import timesforge.product

PYPROJECT = pathlib.Path(os.path.join(pathlib.Path(__file__).parents[2], 'pyproject.toml'))
CONTENT = tomllib.loads(PYPROJECT.read_text(encoding = 'utf-8'))['project']

def test_product_pyproject() -> None:

    assert CONTENT['name'] == timesforge.product.NAME
    assert CONTENT['description'] == timesforge.product.SUMMARY
    assert CONTENT['version'] == timesforge.product.VERSION
    assert timesforge.product.COMMAND in CONTENT['scripts']
