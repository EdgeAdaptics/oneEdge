package oneedge.mqtt

default allow = false

topic_prefix := "sensors/"

allow {
  valid_spiffe_id
  not is_quarantined
  method_allowed
  topic_allowed
}

valid_spiffe_id {
  startswith(input.spiffe_id, "spiffe://oneedge.local/device/")
}

is_quarantined {
  data.overrides.quarantine[input.spiffe_id]
}

method_allowed {
  input.method == "publish"
}

topic_allowed {
  startswith(input.topic, topic_prefix)
}

allow_reason[msg] {
  allow
  msg := sprintf("allow %s to %s", [input.spiffe_id, input.topic])
}

deny_reason[msg] {
  not allow
  msg := message
}

message := msg {
  not valid_spiffe_id
  msg := "workload is not a device"
}

message := msg {
  valid_spiffe_id
  is_quarantined
  msg := "device quarantined"
}

message := msg {
  valid_spiffe_id
  not is_quarantined
  not method_allowed
  msg := sprintf("method %s not allowed", [input.method])
}

message := msg {
  valid_spiffe_id
  not is_quarantined
  method_allowed
  not topic_allowed
  msg := sprintf("topic %s not allowed", [input.topic])
}
