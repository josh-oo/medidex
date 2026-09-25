FROM alpine:3.22
RUN apk add --no-cache curl postgresql-client
RUN apk add --no-cache curl jq postgresql-client
COPY ops/app-init/init.sh /app-init/init.sh
COPY ops/app-init/data/placeholder.pdf /app-init/data/placeholder.pdf
RUN chmod +x /app-init/init.sh
ENTRYPOINT ["sh", "/app-init/init.sh"]
