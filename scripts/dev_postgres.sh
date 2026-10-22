#!/usr/bin/env bash
# scripts/dev_postgres.sh — run a real PostgreSQL + pgvector for local testing.
#
# WHY THIS EXISTS
#   The production target is PostgreSQL + pgvector (Neon / R2 / VPS), but the
#   default test setup is SQLite. Historically the Postgres code path
#   (asyncpg pool, pg_compat placeholder translation, pgvector KNN) was never
#   executed end to end. This script builds a throwaway Postgres cluster so
#   the same test suite can run against a real Postgres.
#
# WHAT IT DOES
#   1. Uses the PostgreSQL 18 server already installed on the machine
#      (/usr/lib/postgresql/18). No root, no Docker, no system changes.
#   2. Compiles pgvector from source into a private prefix and points the
#      server at it via `extension_control_path` (PG18) + `dynamic_library_path`.
#   3. initdb's a private cluster in $PGHOME, starts it on port 5433 and
#      creates the `botbase` role + `botbase` database.
#
# USAGE
#   bash scripts/dev_postgres.sh start     # build (once) + init + start
#   bash scripts/dev_postgres.sh stop      # stop the cluster
#   bash scripts/dev_postgres.sh status    # is it up?
#   bash scripts/dev_postgres.sh env       # print the DSN to use
#
#   export DATABASE_URL="postgresql://botbase:botbase_pw@127.0.0.1:5433/botbase"
#   cd backend && PYTHONPATH=. .venv/bin/python -m pytest app/tests/ -q
#
# NOTES
#   - The cluster is private to $HOME and holds no customer data.
#   - pgvector 0.8.2+ is required for PostgreSQL 18 (0.8.0 fails to compile:
#     the TupleDescData.attrs change).
#   - The `vector` extension must exist before the app role can use it; the
#     script creates it as the superuser so a non-superuser app role works.
set -euo pipefail

PGHOME="${PGHOME:-$HOME/.local/share/botbase-pg}"
PGBIN="${PGBIN:-/usr/lib/postgresql/18/bin}"
PGPORT="${PGPORT:-5433}"
PGUSER_NAME="${PGUSER_NAME:-botbase}"
PGPASSWORD_VALUE="${PGPASSWORD_VALUE:-botbase_pw}"
PGDATABASE_NAME="${PGDATABASE_NAME:-botbase}"
PGVECTOR_VERSION="${PGVECTOR_VERSION:-v0.8.2}"
DEB_URL="${DEB_URL:-http://http.kali.org/kali/pool/main/p/postgresql-18/postgresql-server-dev-18_18.6-3_amd64.deb}"

log() { printf '\033[1;34m[dev-postgres]\033[0m %s\n' "$*"; }
die() { printf '\033[1;31m[dev-postgres] %s\033[0m\n' "$*" >&2; exit 1; }

build_pgvector() {
  if [ -f "$PGHOME/lib/vector.so" ] && [ -f "$PGHOME/share/extension/vector.control" ]; then
    log "pgvector already built"
    return
  fi
  command -v curl >/dev/null || die "curl is required"
  command -v gcc >/dev/null || die "gcc is required"
  command -v make >/dev/null || die "make is required"

  mkdir -p "$PGHOME/src" "$PGHOME/lib" "$PGHOME/share/extension" "$PGHOME/bin"

  # Server headers (pg_config points at an include dir that is not installed
  # by default). The .deb is unpacked into the private prefix; nothing is
  # written outside $PGHOME.
  if [ ! -d "$PGHOME/pgdev/usr/include/postgresql/18/server" ]; then
    log "fetching PostgreSQL server headers"
    curl -sL -o "$PGHOME/src/pgdev.deb" "$DEB_URL"
    dpkg-deb -x "$PGHOME/src/pgdev.deb" "$PGHOME/pgdev"
  fi

  log "fetching pgvector $PGVECTOR_VERSION"
  curl -sL -o "$PGHOME/src/pgvector.tar.gz" \
    "https://codeload.github.com/pgvector/pgvector/tar.gz/refs/tags/$PGVECTOR_VERSION"
  tar -xzf "$PGHOME/src/pgvector.tar.gz" -C "$PGHOME/src"

  # A pg_config wrapper so the build uses our headers and installs into our
  # prefix (the system directories are not writable).
  cat > "$PGHOME/bin/pg_config" <<EOF
#!/bin/sh
REAL="${PGBIN}/pg_config"
case "\$1" in
  --includedir-server) echo "$PGHOME/pgdev/usr/include/postgresql/18/server" ;;
  --includedir) echo "$PGHOME/pgdev/usr/include/postgresql" ;;
  --pkglibdir) echo "$PGHOME/lib" ;;
  --sharedir) echo "$PGHOME/share" ;;
  *) exec \$REAL "\$@" ;;
esac
EOF
  chmod +x "$PGHOME/bin/pg_config"

  log "compiling pgvector"
  make -C "$PGHOME/src/pgvector-${PGVECTOR_VERSION#v}" USE_PGXS=1 \
    PG_CONFIG="$PGHOME/bin/pg_config" \
    CPPFLAGS="-I$PGHOME/pgdev/usr/include/postgresql/18/server" -j"$(nproc)" \
    > "$PGHOME/src/build.log" 2>&1 \
    || { tail -20 "$PGHOME/src/build.log"; die "pgvector build failed"; }

  make -C "$PGHOME/src/pgvector-${PGVECTOR_VERSION#v}" USE_PGXS=1 \
    PG_CONFIG="$PGHOME/bin/pg_config" install \
    > "$PGHOME/src/install.log" 2>&1 || true

  # module_pathname must resolve through dynamic_library_path.
  sed -i "s|^module_pathname.*|module_pathname = 'vector'|" \
    "$PGHOME/share/extension/vector.control"

  # Copy the contrib control files next to ours so one directory serves both.
  cp -a /usr/share/postgresql/18/extension/*.control \
        /usr/share/postgresql/18/extension/*.sql "$PGHOME/share/extension/" 2>/dev/null || true
}

init_cluster() {
  if [ -f "$PGHOME/data/PG_VERSION" ]; then
    log "cluster already initialised"
    return
  fi
  mkdir -p "$PGHOME/data" "$PGHOME/run"
  echo "$PGPASSWORD_VALUE" > "$PGHOME/pw.txt"
  "$PGBIN/initdb" -D "$PGHOME/data" -U postgres \
    --auth-local=trust --auth-host=scram-sha-256 \
    --pwfile="$PGHOME/pw.txt" -E UTF8 > "$PGHOME/initdb.log" 2>&1 \
    || { tail -20 "$PGHOME/initdb.log"; die "initdb failed"; }

  cat >> "$PGHOME/data/postgresql.conf" <<EOF

# --- BotBase local dev cluster ---
port = $PGPORT
listen_addresses = '127.0.0.1'
unix_socket_directories = '$PGHOME/run'
dynamic_library_path = '\$libdir:$PGHOME/lib'
extension_control_path = '$PGHOME/share'
EOF
}

start_cluster() {
  if "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" >/dev/null 2>&1; then
    log "cluster already running on $PGPORT"
    return
  fi
  "$PGBIN/pg_ctl" -D "$PGHOME/data" -l "$PGHOME/pg.log" start
  sleep 2
  "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" >/dev/null || die "cluster did not start"
}

seed_role_and_db() {
  export PGPASSWORD="$PGPASSWORD_VALUE"
  if ! "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U postgres -d postgres -tAc \
      "SELECT 1 FROM pg_roles WHERE rolname='$PGUSER_NAME'" | grep -q 1; then
    "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U postgres -d postgres -q \
      -c "CREATE ROLE $PGUSER_NAME LOGIN PASSWORD '$PGPASSWORD_VALUE' SUPERUSER;"
  fi
  if ! "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U postgres -d postgres -tAc \
      "SELECT 1 FROM pg_database WHERE datname='$PGDATABASE_NAME'" | grep -q 1; then
    "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U postgres -d postgres -q \
      -c "CREATE DATABASE $PGDATABASE_NAME OWNER $PGUSER_NAME;"
  fi
  "$PGBIN/psql" -h 127.0.0.1 -p "$PGPORT" -U "$PGUSER_NAME" -d "$PGDATABASE_NAME" -q \
    -c "CREATE EXTENSION IF NOT EXISTS vector;" \
    -c "CREATE EXTENSION IF NOT EXISTS pg_trgm;"
}

case "${1:-start}" in
  start)
    build_pgvector
    init_cluster
    start_cluster
    seed_role_and_db
    log "ready: postgresql://$PGUSER_NAME:$PGPASSWORD_VALUE@127.0.0.1:$PGPORT/$PGDATABASE_NAME"
    ;;
  stop)
    "$PGBIN/pg_ctl" -D "$PGHOME/data" stop || true
    log "stopped"
    ;;
  status)
    "$PGBIN/pg_isready" -h 127.0.0.1 -p "$PGPORT" && echo "up" || echo "down"
    ;;
  env)
    echo "postgresql://$PGUSER_NAME:$PGPASSWORD_VALUE@127.0.0.1:$PGPORT/$PGDATABASE_NAME"
    ;;
  *)
    die "usage: $0 {start|stop|status|env}"
    ;;
esac
