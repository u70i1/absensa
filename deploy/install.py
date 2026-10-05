"""Delegate the legacy entry point to the verified HTTPS release installer."""
import os
from pathlib import Path

if __name__ == "__main__":
    installer = Path(__file__).resolve().parents[1] / "install.sh"
    print("Pemasang lama telah diganti. Membuka installer rilis Absensa…", flush=True)
    os.execv("/bin/bash", ["bash", str(installer)])
