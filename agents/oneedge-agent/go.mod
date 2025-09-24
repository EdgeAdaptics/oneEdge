module github.com/EdgeAdaptics/oneEdge/agents/oneedge-agent

go 1.21

require (
	github.com/eclipse/paho.mqtt.golang v1.4.3
	github.com/spiffe/go-spiffe/v2 v2.1.6
)

require (
	github.com/Microsoft/go-winio v0.6.0 // indirect
	github.com/go-jose/go-jose/v3 v3.0.0 // indirect
	github.com/golang/protobuf v1.5.2 // indirect
	github.com/gorilla/websocket v1.5.3 // indirect
	github.com/zeebo/errs v1.3.0 // indirect
	golang.org/x/crypto v0.23.0 // indirect
	golang.org/x/mod v0.12.0 // indirect
	golang.org/x/net v0.25.0 // indirect
	golang.org/x/sync v0.1.0 // indirect
	golang.org/x/sys v0.20.0 // indirect
	golang.org/x/text v0.15.0 // indirect
	golang.org/x/tools v0.12.1 // indirect
	google.golang.org/genproto v0.0.0-20230223222841-637eb2293923 // indirect
	google.golang.org/grpc v1.53.0 // indirect
	google.golang.org/protobuf v1.28.1 // indirect
)

replace golang.org/x/crypto => golang.org/x/crypto v0.18.0

replace golang.org/x/mod => golang.org/x/mod v0.12.0

replace golang.org/x/net => golang.org/x/net v0.25.0

replace golang.org/x/sys => golang.org/x/sys v0.20.0

replace golang.org/x/text => golang.org/x/text v0.14.0

replace golang.org/x/tools => golang.org/x/tools v0.1.12
