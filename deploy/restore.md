# Restoring the database

The nightly `deploy/backup.sh` writes a custom-format `pg_dump` to
`<bucket>/backups/pg/<timestamp>.dump`. This is how you get it back.

## 0. Before anything else: practise on a scratch database

A restore you have never run is not a backup. Do this once before launch,
and again after any change to the schema:

```bash
# on the VPS
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml \
  exec -T db createdb -U botbase botbase_restore_test

# stream the newest dump into the scratch database
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml \
  exec -T backend python scripts/backup_postgres_to_r2.py --list   # (see below)

# download the dump and restore it
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml \
  exec -T db pg_restore -U botbase -d botbase_restore_test --clean --if-exists < /tmp/latest.dump

# sanity check
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml \
  exec -T db psql -U botbase -d botbase_restore_test -c "SELECT count(*) FROM users;"
```

## 1. Downloading a dump

The dumps live in the bucket under `backups/pg/`. With the `aws` CLI:

```bash
aws s3 cp s3://botbase-prod/backups/pg/<timestamp>.dump ./latest.dump --endpoint-url https://<account-id>.r2.cloudflarestorage.com
```

or from the API container (it already has the credentials and boto3):

```bash
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml \
  exec -T backend python - <<'PY'
import boto3, os
s3 = boto3.client("s3", endpoint_url=os.environ["S3_ENDPOINT_URL"],
                  aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
                  aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
                  region_name=os.environ.get("S3_REGION", "auto"))
keys = sorted(k["Key"] for k in s3.list_objects_v2(Bucket=os.environ["S3_BUCKET"]).get("Contents", [])
              if k["Key"].startswith("backups/pg/"))
print("\n".join(keys[-5:]))
PY
```

## 2. Restoring over the live database

```bash
# 1. stop the API (the database stays up)
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml stop backend

# 2. restore into the live database
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml \
  exec -T db pg_restore -U botbase -d botbase --clean --if-exists < /tmp/latest.dump

# 3. start the API again and check it
docker compose --env-file /opt/botbase/.env -f docker/compose.prod.yml up -d backend
curl -fsS https://api.yourdomain.com/health/ready
```

`--clean` drops the objects that are in the target database but not in the
dump, so the restored state matches the dump exactly.

## 3. Restoring onto a different machine

The dump is portable: it only needs `pg_dump`/`pg_restore` from the same
PostgreSQL major version (16 here) and the `vector` extension available in
the target database.

```bash
createdb botbase
psql -d botbase -c "CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;"
pg_restore -d botbase --no-owner < latest.dump
```

## 4. What is NOT in the dump

- **Uploaded files** live in object storage (R2) and are *not* part of the
  database dump. The bucket is versioned; keep its lifecycle rules so old
  versions survive long enough to recover from a bad delete.
- **Agent icons** are stored on the container volume (`uploads` volume).
  Copy the volume (`docker run --rm -v botbase_uploads:/data -v "$PWD":/backup
  alpine tar czf /backup/uploads.tgz /data`) if you want them off the box.
- **The `alembic_version` table** is in the dump, so the schema revision
  travels with the data.
