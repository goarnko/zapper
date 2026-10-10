"""Entry script for PyInstaller, which needs a plain script rather than
`python -m zaptv` (zaptv/__main__.py uses a relative import)."""

from zaptv.main import main

raise SystemExit(main())
