FROM python:3.11.2-slim

EXPOSE 5000
VOLUME /var/mezcal/images

ENV MEZCAL_STORAGE_DIR=/var/mezcal/images

WORKDIR /opt/mezcal
COPY src pyproject.toml /opt/mezcal/
RUN pip install .

ENTRYPOINT ["mezcal"]
