package oneedge.mqtt

default allow = false

spiffe_id := input.attributes.source.principal

method := m {
  m := input.attributes.context.extensions.method
} else = "publish"

topic := t {
  t := input.attributes.context.extensions.topic
} else = "sensors/dev/agent/telemetry"

allow {
  startswith(spiffe_id, "spiffe://oneedge.local/device/")
  not data.overrides.quarantine[spiffe_id]
}

deny[msg] {
  not allow
  msg := reason
}

reason := "workload SPIFFE ID outside device namespace" {
  not startswith(spiffe_id, "spiffe://oneedge.local/device/")
}

reason := "device quarantined" {
  startswith(spiffe_id, "spiffe://oneedge.local/device/")
  data.overrides.quarantine[spiffe_id]
}
