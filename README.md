# Relic Radiation Absorber

An absorber that captures the relic radiation from the cosmic web. This HTTP sink stores every application-visible inbound request and turns its bytes into a WAV file.

## Run

For local development:

```sh
DATA_DIR=./captures uv run python app.py
```

Or with Docker:

```sh
docker build -t relic-radiation .
docker run --rm -p 8080:8080 -v "$PWD/captures:/data" relic-radiation
curl -X SCRAPE -H 'Authorization: Bearer example' --data-binary 'hello' http://localhost:8080/a/path
```

Each accepted request creates `/data/<id>/metadata.json`, `body.bin`, and, shortly afterward, `request.wav`. The response is `202` with the capture ID. Bodies over 10 MiB are rejected. Files remain until manually deleted.

The WAV deterministically maps every byte of a canonical request (request line, headers, and exact body) to a short tone. It is not speech. HTTP parsing removes wire details such as chunk framing, and TLS is terminated before the service sees a request.

## Security

This service intentionally stores authorization headers, cookies, and bodies without redaction. Do not expose `/data`, do not put secrets in logs, mount storage with appropriate host permissions, and restrict host access. Public ingestion permits deliberate disk exhaustion; apply a reverse-proxy request-rate limit and monitor disk usage before exposing it to the internet.

## Test

```sh
python -m unittest -v
```
