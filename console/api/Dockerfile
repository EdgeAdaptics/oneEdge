FROM golang:1.21 AS build
WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download
COPY . .
RUN CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o /out/console-api ./cmd/console-api

FROM gcr.io/distroless/base-debian12:nonroot
COPY --from=build /out/console-api /bin/console-api
ENV PORT=8080
USER nonroot:nonroot
ENTRYPOINT ["/bin/console-api"]
