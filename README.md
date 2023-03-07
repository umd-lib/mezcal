# mezcal

Mezzanine Caching and Access Layer Web Application

## Purpose

Mezcal serves as an intermediary microservice between a repository storing
preservation masters of digital object images (typically in a storage- and
bandwidth-intensive format such as TIFF) and a IIIF image server
that delivers these images over the web. As its name suggests, it stores
and serves mezzanine-quality versions of the digital object images as JPEGs.

## Development Environment

Python version: 3.11

### Installation

```bash
git clone git@github.com:umd-lib/mezcal.git
cd mezcal
pyenv install --skip-existing $(cat .python-version)
python -m venv .venv --prompt mezcal-py$(cat .python-version)
pip install -r requirements.txt -e .
```

### Configuration

Create a `.env` file with the following contents:

```bash
# authentication token for the origin repository
JWT_TOKEN=...
# base URL to the origin repository
REPO_BASE_URL=...
# local storage directory
STORAGE_DIR=image_cache
# storage directory layout
# allowed values are "basic", "md5_encoded", and "md5_encoded_pairtree"
STORAGE_LAYOUT=basic
# enable debugging and hot reloading when run via "flask run"
FLASK_DEBUG=1
```

### Running

To run the application in debug mode, with hot code reloading:

```bash
flask --app mezcal.web:app run
```

To run the application in production mode, using the [waitress] WSGI server:

```bash
mezcal
```

Either way, the application will be available at <http://localhost:5000/>

### Deploying using Docker

Build the image:

```bash
docker build -t docker.lib.umd.edu/mezcal:latest .
```

If you need to build for multiple architectures (e.g., AMD and ARM), you 
can use `docker buildx`. This assumes you have a builder named "local" 
configured for use with your docker buildx system, and you are logged in 
to a Docker repository that you can push images to:

```bash
docker buildx build --builder local --platform linux/amd64,linux/arm64 \
    -t docker.lib.umd.edu/mezcal:latest --push .
    
# then pull the image so it is available locally
docker pull docker.lib.umd.edu/mezcal:latest
```

Create a volume to store the mezzanine files:

```bash
docker volume create mezcal-cache
```

Run the container:

```bash
docker run -d -p 5000:5000 \
    -v mezcal-cache:/var/cache/mezcal \
    -e JWT_TOKEN=... \
    -e REPO_BASE_URL=... \
    -e STORAGE_DIR=/var/cache/mezcal \
    -e STORAGE_LAYOUT=basic \
    docker.lib.umd.edu/mezcal:latest
```

If you created a `.env` file (see [Configuration](#configuration)), you 
can run the Docker image using that file. If you mount a `mezcal-cache` 
volume, you should make sure that your `STORAGE_DIR` is `/var/cache/mezcal`.

```bash
docker run -d -p 5000:5000 \
    -v mezcal-cache:/var/cache/mezcal \
    --env-file .env \
    docker.lib.umd.edu/mezcal:latest
```

[pyenv]: https://github.com/pyenv/pyenv
[waitress]: https://pypi.org/project/waitress/
