FROM alpine:3.22
RUN apk add --no-cache curl
COPY app-init/init.sh /app-init/init.sh
RUN chmod +x /app-init/init.sh
ENTRYPOINT ["sh", "/app-init/init.sh"]
