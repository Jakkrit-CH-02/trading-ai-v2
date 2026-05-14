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

import "github.com/gofiber/fiber/v2"

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

// OK writes a successful envelope with the given data payload.
func OK(c *fiber.Ctx, data interface{}) error {
	return c.JSON(Envelope{Data: data, Error: nil})
}

// Err writes a failed envelope with the given HTTP status, code, and message.
func Err(c *fiber.Ctx, status int, code, msg string) error {
	return c.Status(status).JSON(Envelope{
		Data:  nil,
		Error: &APIError{Code: code, Message: msg},
	})
}

// ErrDetails writes a failed envelope including a structured details payload.
func ErrDetails(c *fiber.Ctx, status int, code, msg string, details interface{}) error {
	return c.Status(status).JSON(Envelope{
		Data:  nil,
		Error: &APIError{Code: code, Message: msg, Details: details},
	})
}
