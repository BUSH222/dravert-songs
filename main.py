"""Run the site: `uv run main.py` (add --reload while developing)."""

import argparse

import uvicorn


def main() -> None:
    parser = argparse.ArgumentParser(description="Песни на стихи П.Л. Драверта")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--reload", action="store_true", help="restart on code changes (development)")
    parser.add_argument("--proxy", action="store_true", help="trust X-Forwarded-* headers from a local reverse proxy")
    args = parser.parse_args()
    uvicorn.run(
        "app.main:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_dirs=["app"] if args.reload else None,
        proxy_headers=args.proxy,
        forwarded_allow_ips="127.0.0.1" if args.proxy else None,
    )


if __name__ == "__main__":
    main()
