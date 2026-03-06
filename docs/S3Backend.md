# S3 Storage Backend

Mezcal supports two storage backends for caching mezzanine JPEG images:

- **`local`** (default) — stores images on a local filesystem
- **`s3`** — stores images in an Amazon S3 bucket

The backend is selected at startup via the `MEZCAL_STORAGE_BACKEND` environment
variable. Both backends support the same `MEZCAL_STORAGE_LAYOUT` options and the
same API endpoints.

## How the S3 Backend Works

When `MEZCAL_STORAGE_BACKEND=s3` is set:

1. **On `GET /images/<path>`** — mezcal checks whether the mezzanine JPEG already
   exists in S3 (`HeadObject`). If not, it fetches the source image from the origin
   repository, converts it to JPEG (applying EXIF orientation and mode conversion as
   needed), and uploads the result directly to S3 (`PutObject`). Once the object is
   confirmed to exist, mezcal returns an HTTP `302` redirect to a presigned S3 URL.
   The client fetches the image directly from S3 — mezcal is not in the read path.

2. **On `DELETE /images/<path>`** — mezcal deletes the object from S3
   (`DeleteObject`). Deleting an object that does not exist is a no-op.

3. **Locking** — to prevent duplicate concurrent conversions of the same image,
   mezcal uses a file-based advisory lock stored in the system temp directory
   (`tempfile.gettempdir()`), keyed by an MD5 hash of the S3 object key. This is
   sufficient for single-instance deployments. In a multi-replica deployment, two
   instances may independently convert and upload the same image; since both produce
   identical output, the last writer wins and no data is corrupted.

4. **AWS credentials** — the S3 client uses the standard boto3 credential chain
   (environment variables, `~/.aws/credentials`, EC2 instance profile, EKS IRSA,
   etc.). No AWS credentials are configured in mezcal directly.

## Configuration

### Required

| Variable | Description |
|---|---|
| `MEZCAL_STORAGE_BACKEND` | Set to `s3` to enable S3 storage |
| `MEZCAL_S3_BUCKET` | Name of the S3 bucket to use |

### Optional

| Variable | Default | Description |
|---|---|---|
| `MEZCAL_S3_PREFIX` | _(empty)_ | Key prefix within the bucket (e.g. `mezcal/cache`). A trailing `/` is added automatically if omitted. |
| `MEZCAL_S3_PRESIGNED_URL_EXPIRY` | `3600` | Lifetime in seconds of the presigned URL returned to the client |
| `MEZCAL_STORAGE_LAYOUT` | `basic` | Object key layout strategy. See [Storage Layout](#storage-layout). |
| `TMPDIR` | `/tmp` | Directory used for advisory lock files (see [Lock Files](#lock-files)). Must be writable at runtime. |

All standard `AWS_*` environment variables and boto3 configuration mechanisms are
supported for credentials and region.

### Example `.env` for S3

```dotenv
MEZCAL_STORAGE_BACKEND=s3
MEZCAL_S3_BUCKET=my-mezcal-cache
MEZCAL_S3_PREFIX=cache
MEZCAL_S3_PRESIGNED_URL_EXPIRY=3600
MEZCAL_STORAGE_LAYOUT=basic
MEZCAL_JWT_TOKEN=...
MEZCAL_REPO_BASE_URL=...
AWS_DEFAULT_REGION=us-east-1
```

### Example Docker run

```bash
docker run -d -p 5000:5000 \
    -e MEZCAL_STORAGE_BACKEND=s3 \
    -e MEZCAL_S3_BUCKET=my-mezcal-cache \
    -e MEZCAL_S3_PREFIX=cache \
    -e MEZCAL_JWT_TOKEN=... \
    -e MEZCAL_REPO_BASE_URL=... \
    -e AWS_DEFAULT_REGION=us-east-1 \
    -e AWS_ACCESS_KEY_ID=... \
    -e AWS_SECRET_ACCESS_KEY=... \
    docker.lib.umd.edu/mezcal:latest
```

In Kubernetes with IRSA, omit the `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`
variables and annotate the service account instead.

## Lock Files

To prevent duplicate concurrent conversions of the same image, mezcal writes
advisory lock files to `tempfile.gettempdir()`, which resolves to:

- **The value of `TMPDIR`** if that environment variable is set
- **`/tmp`** otherwise (the default on Linux, including Docker and Kubernetes)

Lock files are named `<md5-of-s3-key>.lock` and are small (empty). They are
created on demand and left in place after use (harmless).

### Standard Docker containers

No action required. `/tmp` is writable by default in Docker containers because
it is part of the container's writable layer.

### Kubernetes with `readOnlyRootFilesystem: true`

If the pod's security context sets `readOnlyRootFilesystem: true`, the entire
root filesystem — including `/tmp` — is read-only. Lock file creation will fail
at runtime with a `PermissionError`, causing every image request to return a 500.

Fix this by mounting a writable `emptyDir` volume at `/tmp`:

```yaml
spec:
  containers:
    - name: mezcal
      securityContext:
        readOnlyRootFilesystem: true
      volumeMounts:
        - name: tmp
          mountPath: /tmp
  volumes:
    - name: tmp
      emptyDir: {}
```

Alternatively, mount the `emptyDir` at a different path and point mezcal at it
via the `TMPDIR` environment variable:

```yaml
      env:
        - name: TMPDIR
          value: /run/mezcal-locks
      volumeMounts:
        - name: locks
          mountPath: /run/mezcal-locks
  volumes:
    - name: locks
      emptyDir: {}
```

## Storage Layout

The `MEZCAL_STORAGE_LAYOUT` setting controls how the origin repository path is
mapped to an S3 object key (or local filesystem path). All three options are
available for both backends.

| Layout | S3 key for `some/repo/path` |
|---|---|
| `basic` | `<prefix>/some/repo/path/image.jpg` |
| `md5_encoded` | `<prefix>/<md5(some/repo/path)>/image.jpg` |
| `md5_encoded_pairtree` | `<prefix>/<xx>/<yy>/<zz>/<md5>/image.jpg` |

**`basic`** is recommended for new deployments. It mirrors the origin repository
path structure, making object keys predictable and human-readable, and is directly
compatible with Cantaloupe's `S3Source` `BasicLookupStrategy` without a delegate.

## Cantaloupe S3Source Integration

When using the S3 backend, Cantaloupe can be configured to read cached images
directly from S3 using its built-in `S3Source`, bypassing mezcal entirely for
reads. This allows Cantaloupe to use HTTP range requests to fetch only the bytes
needed for each IIIF tile rather than downloading the full JPEG.

### Recommended approach

1. Configure mezcal with `MEZCAL_STORAGE_BACKEND=s3` and `MEZCAL_STORAGE_LAYOUT=basic`.

2. Configure Cantaloupe to use `S3Source` with `BasicLookupStrategy`:

   ```properties
   source.static = S3Source
   S3Source.bucket.name = my-mezcal-cache
   S3Source.BasicLookupStrategy.path_prefix = cache/
   S3Source.BasicLookupStrategy.path_suffix = /image.jpg
   ```

3. To trigger on-demand conversion (so Cantaloupe never tries to read an object
   that does not yet exist), implement a Cantaloupe delegate method
   `s3source_object_info()` that first calls mezcal's `GET /images/<path>` endpoint.
   Mezcal will perform the conversion and upload if needed, then return a `302`.
   The delegate ignores the redirect and returns the S3 key to `S3Source`, which
   reads directly from S3:

   ```ruby
   def s3source_object_info(options = {})
     identifier = context['identifier']
     # trigger on-demand conversion in mezcal; ignore the redirect
     uri = URI.parse("http://mezcal:5000/images/#{CGI.escape(identifier)}")
     Net::HTTP.get_response(uri)
     # return the key for S3Source to use
     { 'bucket' => 'my-mezcal-cache', 'key' => "cache/#{identifier}/image.jpg" }
   end
   ```

## Migrating an Existing Cache from Filesystem to S3

If you have an existing mezzanine cache on a local filesystem volume, use
`aws s3 sync` to copy it to S3. The tool uploads in parallel, validates each
object's `Content-MD5` server-side, and skips objects that already exist.

### Step 1 — Live sync (mezcal running)

```bash
aws s3 sync /var/cache/mezcal/ s3://my-mezcal-cache/cache/ \
    --exclude 'lost+found/*' \
    --no-progress
```

This will take some time for large caches. Mezcal continues serving requests
normally during this step.

### Step 2 — Final sync (mezcal stopped)

Stop mezcal, then run a second pass to catch any files written in the interim:

```bash
aws s3 sync /var/cache/mezcal/ s3://my-mezcal-cache/cache/ \
    --exclude 'lost+found/*' \
    --size-only
```

`--size-only` skips re-uploading objects where size matches, avoiding the need to
re-download everything from S3 to compare checksums. Mezzanine images are
write-once, so a size match is a reliable signal.

### Step 3 — Switch mezcal to S3

Update the mezcal deployment to set:

```dotenv
MEZCAL_STORAGE_BACKEND=s3
MEZCAL_S3_BUCKET=my-mezcal-cache
MEZCAL_S3_PREFIX=cache
```

Restart mezcal. The existing local volume can be decommissioned once the S3
deployment is confirmed stable.
