FROM golang:1.25-alpine AS builder

RUN apk add --no-cache git

WORKDIR /src

COPY go.mod go.sum ./
RUN go mod download

COPY . .

RUN CGO_ENABLED=0 go build -o /bin/api ./cmd/api
RUN CGO_ENABLED=0 go build -o /bin/bot ./cmd/bot

FROM alpine:3.20

RUN apk add --no-cache ca-certificates tzdata

COPY --from=builder /bin/api /bin/api
COPY --from=builder /bin/bot /bin/bot
COPY --from=builder /src/config /app/config
COPY --from=builder /src/migrations /app/migrations

WORKDIR /app

EXPOSE 8080

CMD ["/bin/api", "-config", "config/config.dev.yaml"]
