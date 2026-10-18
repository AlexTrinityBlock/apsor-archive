"""Command-line entry point for the API."""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the DendroMatrix API.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    arguments = parser.parse_args()
    uvicorn.run(
        "app.main:app",
        host=arguments.host,
        port=arguments.port,
        reload=arguments.reload,
    )
