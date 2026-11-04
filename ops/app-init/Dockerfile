FROM alpine:3.22
# No postgres client: app-init never touches postgres (see init.sh).
RUN apk add --no-cache curl jq
COPY ops/app-init/init.sh /app-init/init.sh
RUN chmod +x /app-init/init.sh
ENTRYPOINT ["sh", "/app-init/init.sh"]
