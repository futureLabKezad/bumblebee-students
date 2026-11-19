The Flight ("Полёт") web module of the app.

build_app.sh copies the built page here before the build:
    flight_embedded.html   from gcs/web/dist (python3 gcs/web/build_html.py)
    pyodide/               from gcs/web/dist/pyodide, if gcs/web/fetch_pyodide.py was run

Both are build products and are not checked in (see ../../../.gitignore). This file keeps the
folder in the repository: Package.swift copies the folder into the app bundle as it is, and
FlightView.swift serves flight_embedded.html and the five Pyodide files to its WKWebView.
Without the page the Flight section says that the module files are missing.
