FROM python:3.11.2-slim

EXPOSE 5000
VOLUME /var/mezcal/images

ENV STORAGE_DIR=/var/mezcal/images

WORKDIR /opt/mezcal
COPY requirements.txt /opt/mezcal/
RUN pip install -r requirements.txt
COPY . /opt/mezcal/
RUN pip install -e .

CMD ["mezcal"]
