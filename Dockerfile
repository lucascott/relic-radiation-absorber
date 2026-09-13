FROM python:3.14-slim

ARG DATA_DIR=/data
ENV DATA_DIR=$DATA_DIR
RUN mkdir -p "$DATA_DIR" && chown nobody:nogroup "$DATA_DIR"

WORKDIR /app
COPY . .

USER nobody:nogroup

CMD ["python", "-u", "app.py"]
