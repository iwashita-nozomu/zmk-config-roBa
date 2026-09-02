# syntax=docker/dockerfile:1.7
FROM docker.io/zmkfirmware/zmk-build-arm@sha256:840526f03c19c286b614d5cb97b11242ae19e468fc2ef2f095f6cf0465fa1c5b

COPY toolchain/keymap-drawer-requirements.txt /tmp/keymap-drawer-requirements.txt

RUN python3 -c 'import sys; assert sys.version_info[:2] == (3, 12), sys.version' \
 && python3 -c "import urllib.request; urllib.request.urlretrieve('https://files.pythonhosted.org/packages/5d/95/6b5cb3461ea5673ba0995989746db58eb18b91b54dbf331e72f569540946/pip-26.1.2-py3-none-any.whl', '/tmp/pip.whl')" \
 && echo "382ff9f685ee3bc25864f820aa50505825f10f5458ffff07e30a6d96e5715cab  /tmp/pip.whl" | sha256sum --check - \
 && PYTHONPATH=/tmp/pip.whl python3 -m pip install \
      --disable-pip-version-check \
      --no-cache-dir \
      --no-deps \
      --only-binary=:all: \
      --require-hashes \
      --target /opt/keymap-drawer \
      --requirement /tmp/keymap-drawer-requirements.txt \
 && PYTHONPATH=/opt/keymap-drawer python3 -m keymap_drawer --help >/dev/null \
 && rm -f /tmp/pip.whl /tmp/keymap-drawer-requirements.txt

COPY toolchain/versions.env /opt/zmk-config-roba/versions.env
COPY toolchain/zmk_toolchain.py /usr/local/bin/zmk-toolchain

ENV PYTHONPATH=/opt/keymap-drawer
ENV ZMK_CONFIG_ROOT=/workspace
ENV ZMK_TOOLCHAIN_LOCK=/opt/zmk-config-roba/versions.env

LABEL org.opencontainers.image.base.name="docker.io/zmkfirmware/zmk-build-arm@sha256:840526f03c19c286b614d5cb97b11242ae19e468fc2ef2f095f6cf0465fa1c5b" \
      org.opencontainers.image.title="zmk-config-roBa build environment" \
      org.opencontainers.image.description="Issue #164 pinned ZMK firmware and keymap build environment"

ENTRYPOINT ["python3", "/usr/local/bin/zmk-toolchain"]
