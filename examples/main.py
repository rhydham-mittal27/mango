"""examples/main.py

Minimal app entry point using mango.App — the full wrapper, so this file
never imports fastapi. `app` is directly ASGI-callable, so it's also
what `uvicorn examples.main:app` points at.

Classes: none.

Functions (1):
    - create_app: builds the mango app and mounts every registered
      mango module onto it.
"""
import mango
from examples.hello_module import module as hello_module  # noqa: F401  (import registers @mango.module)


def create_app() -> mango.App:
    """Build the mango app and mount every registered mango module."""
    app = mango.App(title="mango example", prefix="/api/v1")  # owns its own FastAPI instance internally
    mount_order = app.mount_all()  # list of module names, in the order they were mounted
    print(f"mounted modules: {mount_order}")

    @app.get("/healthz")
    async def healthz() -> dict:
        """Liveness-check route, registered directly on the app without a full module."""
        return {"status": "ok"}

    return app


app = create_app()  # module-level app instance — ASGI-callable, e.g. for `uvicorn examples.main:app`

if __name__ == "__main__":
    app.run()  # `python examples/main.py` instead of a separate uvicorn command
