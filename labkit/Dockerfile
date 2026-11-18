# Build container: holds the whole toolchain so the build is repeatable on any machine.
# The LEARNER never needs Docker - they only get the compiled program this produces.
#
#   docker build -t siraugga-labkit-build .
#   docker run --rm -v "%cd%\dist:/out" siraugga-labkit-build        -> dist/siraugga-lab (Linux binary)
#
# The Windows .exe is built natively with build_windows.bat (Nuitka cannot cross-compile).
FROM python:3.13-slim-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends gcc libc6-dev make patchelf ccache \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir nuitka zstandard
WORKDIR /src
COPY siraugga_lab ./siraugga_lab
CMD ["sh", "-c", "python -m nuitka --onefile --standalone --include-package=siraugga_lab --include-data-dir=siraugga_lab/labs=siraugga_lab/labs --output-filename=siraugga-lab --output-dir=/out --assume-yes-for-downloads siraugga_lab/__main__.py"]
