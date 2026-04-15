# main.py - kept as a shim so `uvicorn main:app` still works from this directory

from taskflow.app import create_app

app = create_app()


if __name__ == "__main__":
    # `python main.py` is what both READMEs have always documented, and for a
    # while it silently did nothing: the shim built the app, never served it,
    # and exited 0. Delegating to the same CLI the console script uses keeps
    # the two entrypoints from drifting again.
    from taskflow.cli import main

    main()
