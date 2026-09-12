FROM python:3.14-slim

WORKDIR /app
COPY app.py .
RUN mkdir /data && chown nobody:nogroup /data
USER nobody
EXPOSE 8080
VOLUME ["/data"]
CMD ["python", "-u", "app.py"]
