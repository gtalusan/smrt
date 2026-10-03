# syntax=docker/dockerfile:1
# SMRT_REF must be a branch or tag (default master). To pin a SHA:
#   RUN git clone --depth 1 "${SMRT_REPO}" /src \
#    && git -C /src fetch --depth 1 origin "${SMRT_REF}" \
#    && git -C /src checkout FETCH_HEAD
FROM alpine:3.20 AS src
ARG SMRT_REPO=https://github.com/gtalusan/smrt.git
ARG SMRT_REF=master
RUN apk add --no-cache git ca-certificates \
    && git clone --depth 1 --branch "${SMRT_REF}" "${SMRT_REPO}" /src

FROM python:3.12-alpine3.20
RUN apk add --no-cache jq mosquitto-clients
WORKDIR /app
COPY --from=src /src/smrt.py /src/discovery.py /src/network.py /src/protocol.py \
                /src/binary.py /src/ifaces.py /src/loglevel.py /src/tp_analyse.py \
                /app/
COPY docker/run.sh /app/run.sh
COPY docker/entrypoint.sh /usr/local/bin/entrypoint.sh
RUN chmod +x /app/run.sh /usr/local/bin/entrypoint.sh
ENTRYPOINT ["/usr/local/bin/entrypoint.sh"]
