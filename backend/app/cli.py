"""Command-line entry point for the API."""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Run DendroMatrix.")
    parser.add_argument(
        "command",
        nargs="?",
        choices=("api", "worker"),
        default="api",
        help="Run the HTTP API (default) or the durable ingestion worker.",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true")
    parser.add_argument(
        "--once",
        action="store_true",
        help="Worker only: process at most one queued job, then exit.",
    )
    arguments = parser.parse_args()
    if arguments.command == "worker":
        from app.worker import main as worker_main

        worker_main(["--once"] if arguments.once else [])
        return
    uvicorn.run(
        "app.main:app",
        host=arguments.host,
        port=arguments.port,
        reload=arguments.reload,
    )
