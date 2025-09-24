package handlers

import (
	"encoding/json"
	"errors"
	"fmt"
	"log/slog"
	"net/http"
	"strings"

	"github.com/go-chi/chi/v5"
	"github.com/google/uuid"

	"github.com/EdgeAdaptics/oneEdge/console/api/internal/events"
	"github.com/EdgeAdaptics/oneEdge/console/api/internal/policy"
	"github.com/EdgeAdaptics/oneEdge/console/api/internal/store"
)

// API wires HTTP handlers for the console service.
type API struct {
	log    *slog.Logger
	store  *store.Store
	events *events.Bus
	policy *policy.Manager
}

// New constructs the API.
func New(log *slog.Logger, st *store.Store, bus *events.Bus, policyMgr *policy.Manager) *API {
	return &API{log: log, store: st, events: bus, policy: policyMgr}
}

// Routes configures the router with v1 endpoints.
func (a *API) Routes(r chi.Router) {
	r.Route("/v1", func(r chi.Router) {
		r.Post("/devices", a.handleDeviceRegister)
		r.Get("/devices", a.handleDevicesList)
		r.Get("/devices/{id}", a.handleDeviceGet)
		r.Post("/devices/{id}:{action}", a.handleDeviceAction)

		r.Post("/policies", a.handlePolicyCreate)
		r.Post("/policies/{id}:test", a.handlePolicyTest)

		r.Get("/events/stream", a.handleEventsStream)
		r.Get("/metrics/fleet", a.handleFleetMetrics)
	})
}

func (a *API) handleDeviceRegister(w http.ResponseWriter, r *http.Request) {
	var payload struct {
		SPIFFEID    string                 `json:"spiffe_id"`
		DisplayName string                 `json:"display_name"`
		Class       string                 `json:"class"`
		Labels      map[string]interface{} `json:"labels"`
	}
	if err := json.NewDecoder(r.Body).Decode(&payload); err != nil {
		writeError(w, http.StatusBadRequest, "invalid payload")
		return
	}

	labels, _ := json.Marshal(payload.Labels)
	device, err := a.store.RegisterDevice(r.Context(), store.RegisterDeviceInput{
		SPIFFEID:    payload.SPIFFEID,
		DisplayName: payload.DisplayName,
		Class:       payload.Class,
		Labels:      labels,
	})
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	a.events.Publish(events.Event{Type: "device.registered", Data: device})
	writeJSON(w, http.StatusCreated, deviceToResponse(device))
}

func (a *API) handleDevicesList(w http.ResponseWriter, r *http.Request) {
	devices, err := a.store.ListDevices(r.Context(), "default")
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}

	resp := make([]map[string]interface{}, 0, len(devices))
	for _, d := range devices {
		resp = append(resp, deviceToResponse(d))
	}
	writeJSON(w, http.StatusOK, resp)
}

func (a *API) handleDeviceGet(w http.ResponseWriter, r *http.Request) {
	idParam := chi.URLParam(r, "id")
	id, err := uuid.Parse(idParam)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid device id")
		return
	}

	device, err := a.store.GetDevice(r.Context(), id)
	if err != nil {
		status := http.StatusInternalServerError
		if errors.Is(err, store.ErrNotFound) {
			status = http.StatusNotFound
		}
		writeError(w, status, err.Error())
		return
	}

	writeJSON(w, http.StatusOK, deviceToResponse(device))
}

func (a *API) handleDeviceAction(w http.ResponseWriter, r *http.Request) {
	idParam := chi.URLParam(r, "id")
	action := chi.URLParam(r, "action")
	id, err := uuid.Parse(idParam)
	if err != nil {
		writeError(w, http.StatusBadRequest, "invalid device id")
		return
	}

	var payload struct {
		Reason string `json:"reason"`
	}
	_ = json.NewDecoder(r.Body).Decode(&payload)

	switch action {
	case "approve":
		a.deviceStatusResponse(w, r, id, "approved", nil)
	case "quarantine":
		a.deviceStatusResponse(w, r, id, "quarantined", &payload.Reason)
	case "blacklist":
		a.deviceStatusResponse(w, r, id, "blacklisted", &payload.Reason)
	case "deauthorize":
		a.deviceStatusResponse(w, r, id, "deauthorized", &payload.Reason)
	case "rotate":
		a.events.Publish(events.Event{Type: "device.rotate", Data: map[string]string{"id": id.String()}})
		writeJSON(w, http.StatusAccepted, map[string]string{"status": "rotation requested"})
	default:
		writeError(w, http.StatusNotFound, "unsupported action")
	}
}

func (a *API) deviceStatusResponse(w http.ResponseWriter, r *http.Request, id uuid.UUID, status string, reason *string) {
	device, err := a.store.UpdateDeviceStatus(r.Context(), id, status, reason)
	if err != nil {
		statusCode := http.StatusInternalServerError
		if errors.Is(err, store.ErrNotFound) {
			statusCode = http.StatusNotFound
		}
		writeError(w, statusCode, err.Error())
		return
	}

	if status == "quarantined" && a.policy != nil {
		if err := a.policy.SetQuarantine(device.SPIFFEID, true); err != nil {
			writeError(w, http.StatusInternalServerError, fmt.Sprintf("update policy overlay: %v", err))
			return
		}
		a.events.Publish(events.Event{Type: "device.quarantine", Data: map[string]string{"spiffe_id": device.SPIFFEID}})
	} else if status == "approved" && a.policy != nil {
		_ = a.policy.SetQuarantine(device.SPIFFEID, false)
		a.events.Publish(events.Event{Type: "device.approved", Data: map[string]string{"spiffe_id": device.SPIFFEID}})
	}

	writeJSON(w, http.StatusOK, deviceToResponse(device))
}

func (a *API) handlePolicyCreate(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusAccepted, map[string]string{"status": "policy staging queued"})
}

func (a *API) handlePolicyTest(w http.ResponseWriter, r *http.Request) {
	writeJSON(w, http.StatusOK, map[string]string{"result": "allow"})
}

func (a *API) handleFleetMetrics(w http.ResponseWriter, r *http.Request) {
	metrics, err := a.store.FleetMetrics(r.Context(), "default")
	if err != nil {
		writeError(w, http.StatusInternalServerError, err.Error())
		return
	}
	writeJSON(w, http.StatusOK, metrics)
}

func (a *API) handleEventsStream(w http.ResponseWriter, r *http.Request) {
	flusher, ok := w.(http.Flusher)
	if !ok {
		writeError(w, http.StatusInternalServerError, "streaming unsupported")
		return
	}

	w.Header().Set("Content-Type", "text/event-stream")
	w.Header().Set("Cache-Control", "no-cache")
	w.Header().Set("Connection", "keep-alive")

	sub := a.events.Subscribe()
	defer a.events.Unsubscribe(sub)

	notify := r.Context().Done()

	for {
		select {
		case <-notify:
			return
		case evt := <-sub:
			payload, _ := json.Marshal(evt.Data)
			fmt.Fprintf(w, "event: %s\n", evt.Type)
			fmt.Fprintf(w, "data: %s\n\n", strings.TrimSpace(string(payload)))
			flusher.Flush()
		}
	}
}

func deviceToResponse(device store.Device) map[string]interface{} {
	resp := map[string]interface{}{
		"id":         device.ID.String(),
		"tenant_id":  device.TenantID,
		"spiffe_id":  device.SPIFFEID,
		"status":     device.Status,
		"created_at": device.CreatedAt,
		"updated_at": device.UpdatedAt,
	}
	if device.DisplayName.Valid {
		resp["display_name"] = device.DisplayName.String
	}
	if device.Class.Valid {
		resp["class"] = device.Class.String
	}
	if len(device.Labels) > 0 {
		var labels map[string]interface{}
		_ = json.Unmarshal(device.Labels, &labels)
		resp["labels"] = labels
	}
	if device.QuarantineReason.Valid {
		resp["quarantine_reason"] = device.QuarantineReason.String
	}
	if device.LastSeen.Valid {
		resp["last_seen"] = device.LastSeen.Time
	}
	return resp
}

func writeJSON(w http.ResponseWriter, status int, payload interface{}) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func writeError(w http.ResponseWriter, status int, message string) {
	writeJSON(w, status, map[string]string{"error": message})
}
