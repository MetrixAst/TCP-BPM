import logging
import os
import uvicorn
import sys


def _configure_logging() -> None:
    level_name = (os.getenv("LOG_LEVEL") or "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
        force=True,
    )


if __name__ == "__main__":
    _configure_logging()
    port = 8004
    if len(sys.argv) > 1:
        try:
            port = int(sys.argv[1])
        except ValueError:
            print(f"Invalid port: {sys.argv[1]}, using default 8000")
    

    try:
        uvicorn.run(
            "app.main:app",
            host="0.0.0.0",
            port=port,
            reload=True,
            log_level="info",
        )
    except OSError as e:
        if "Address already in use" in str(e):
            print(f"\n Port {port} is already in use!")
            print(f" Try running with a different port: python run.py 8001")
            print(f" Or stop the process using port {port}")
        else:
            raise
