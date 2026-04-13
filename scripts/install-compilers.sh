#!/usr/bin/env bash
set -euo pipefail

# =============================================================================
# Install GCC 10+ and Rust on Amazon Linux 2
# Run as root: sudo bash scripts/install-compilers.sh
# =============================================================================

echo "=== Installing compilers for Amazon Linux 2 ==="

# ---------- GCC 10 via source (Amazon Linux 2 has no gcc10 package) ----------
echo ""
echo "[1/2] GCC 10..."

if gcc -dumpversion 2>/dev/null | grep -q "^1[0-9]"; then
    echo "  GCC $(gcc -dumpversion) already installed"
else
    echo "  Installing build dependencies..."
    yum install -y gcc gcc-c++ make bzip2 wget gmp-devel mpfr-devel libmpc-devel -q

    GCC_VERSION="10.5.0"
    cd /tmp

    if [ ! -f "gcc-${GCC_VERSION}.tar.gz" ]; then
        echo "  Downloading GCC ${GCC_VERSION}..."
        wget -q "https://ftp.gnu.org/gnu/gcc/gcc-${GCC_VERSION}/gcc-${GCC_VERSION}.tar.gz"
    fi

    echo "  Extracting..."
    tar xf "gcc-${GCC_VERSION}.tar.gz"
    cd "gcc-${GCC_VERSION}"

    echo "  Configuring (this takes a few minutes)..."
    mkdir -p build && cd build
    ../configure --enable-languages=c,c++ --disable-multilib --prefix=/usr/local/gcc10 2>&1 | tail -1

    echo "  Building (this takes 15-30 minutes)..."
    make -j"$(nproc)" 2>&1 | tail -1

    echo "  Installing..."
    make install

    # Symlink as default
    update-alternatives --install /usr/bin/gcc gcc /usr/local/gcc10/bin/gcc 100
    update-alternatives --install /usr/bin/g++ g++ /usr/local/gcc10/bin/g++ 100
    update-alternatives --install /usr/bin/cc cc /usr/local/gcc10/bin/gcc 100
    update-alternatives --install /usr/bin/c++ c++ /usr/local/gcc10/bin/g++ 100

    # Library path
    echo "/usr/local/gcc10/lib64" > /etc/ld.so.conf.d/gcc10.conf
    ldconfig

    echo "  GCC $(gcc -dumpversion) installed"
    cd /tmp && rm -rf "gcc-${GCC_VERSION}" "gcc-${GCC_VERSION}.tar.gz"
fi

# ---------- Rust via rustup ----------
echo ""
echo "[2/2] Rust..."

if command -v rustc &>/dev/null; then
    echo "  Rust $(rustc --version) already installed"
else
    echo "  Installing rustup..."
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain stable
    source "$HOME/.cargo/env"
    echo "  Rust $(rustc --version) installed"
    echo '  Add to profile: source "$HOME/.cargo/env"'
fi

echo ""
echo "=== Done ==="
echo "GCC: $(gcc --version | head -1)"
echo "Rust: $(rustc --version)"
echo ""
echo "Now run: ./scripts/setup.sh"
