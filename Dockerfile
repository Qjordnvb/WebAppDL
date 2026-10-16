# WebAppDL/Dockerfile

FROM python:3.13.3-alpine


ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive

WORKDIR /app


RUN apk add --no-cache \
    build-base \
    linux-headers \
    musl-dev \
    openssl-dev \
    tzdata

# Instalar dependencias de Python
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copiar el resto del proyecto
COPY . /app/

EXPOSE 8000

CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "webappdl.asgi:application"]
