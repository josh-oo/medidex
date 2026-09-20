FROM alpine:3.22
RUN apk add --no-cache curl postgresql-client
RUN apk add --no-cache curl jq postgresql-client
COPY app-init/init.sh /app-init/init.sh
COPY app-init/placeholder.pdf /app-init/placeholder.pdf
RUN chmod +x /app-init/init.sh
ENTRYPOINT ["sh", "/app-init/init.sh"]
