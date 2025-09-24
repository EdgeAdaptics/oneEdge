package oneedge.mqtt

default allow = false

spiffe_id := input.attributes.source.principal

allow {
  startswith(spiffe_id, "spiffe://oneedge.local/device/")
  not data.overrides.quarantine[spiffe_id]
}

