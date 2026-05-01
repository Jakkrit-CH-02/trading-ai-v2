// Package api defines the HTTP wire envelope shared by every Go service
// endpoint and mirrored on the frontend in apps/frontend/src/lib/api.ts.
//
// Envelope contract (cross-service):
//
//	success: { "data": T,    "error": null }
//	error:   { "data": null, "error": { "code": string, "message": string, "details"?: unknown } }
//
// Conventions enforced by all producers/consumers:
//   - timestamps:  int64 Unix milliseconds, UTC
//   - money:       decimal string, e.g. "0.00012345" (never float)
//   - ids:         lowercase ULID
//   - error.code:  stable kebab/snake string (e.g. "risk_rejected", "not_found",
//     "validation_failed", "forbidden", "internal")
package api

import (
	"encoding/json"
	"log/slog"
	"net/http"
)

// Envelope is the wire format for every JSON response.
// Exactly one of Data or Error is non-nil.
type Envelope struct {
	Data  interface{} `json:"data"`
	Error *APIError   `json:"error"`
}

// APIError is the error part of the envelope. Details is optional and may
// carry validation field maps or other structured context; it is omitted when nil.
type APIError struct {
	Code    string      `json:"code"`
	Message string      `json:"message"`
	Details interface{} `json:"details,omitempty"`
}

// WriteJSON writes a successful envelope with the given data.
func WriteJSON(w http.ResponseWriter, status int, data interface{}) {
	write(w, status, Envelope{Data: data, Error: nil})
}

// WriteError writes a failed envelope with the given code and message.
func WriteError(w http.ResponseWriter, status int, code, msg string) {
	write(w, status, Envelope{Data: nil, Error: &APIError{Code: code, Message: msg}})
}

// WriteErrorWithDetails writes a failed envelope including a structured details payload.
func WriteErrorWithDetails(w http.ResponseWriter, status int, code, msg string, details interface{}) {
	write(w, status, Envelope{Data: nil, Error: &APIError{Code: code, Message: msg, Details: details}})
}

func write(w http.ResponseWriter, status int, body Envelope) {
	w.Header().Set("Content-Type", "application/json; charset=utf-8")
	w.WriteHeader(status)
	if err := json.NewEncoder(w).Encode(body); err != nil {
		slog.Error("api: encode response", "err", err)
	}
}
