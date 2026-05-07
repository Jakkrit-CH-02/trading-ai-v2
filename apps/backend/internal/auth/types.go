package auth

import (
	"errors"
	"time"
)

// Role enumerates user authorization levels.
type Role string

const (
	RoleAdmin    Role = "admin"
	RoleOperator Role = "operator"
	RoleViewer   Role = "viewer"
)

func (r Role) Valid() bool {
	switch r {
	case RoleAdmin, RoleOperator, RoleViewer:
		return true
	}
	return false
}

// User is the persisted account record. PasswordHash is bcrypt.
type User struct {
	ID           string
	Username     string
	PasswordHash string
	Role         Role
	CreatedAt    time.Time
	UpdatedAt    time.Time
}

// PublicUser is the safe-to-return projection (no hash).
type PublicUser struct {
	ID        string `json:"id"`
	Username  string `json:"username"`
	Role      Role   `json:"role"`
	CreatedAt int64  `json:"created_at"`
}

func (u User) Public() PublicUser {
	return PublicUser{
		ID:        u.ID,
		Username:  u.Username,
		Role:      u.Role,
		CreatedAt: u.CreatedAt.UnixMilli(),
	}
}

var (
	ErrUserNotFound     = errors.New("auth: user not found")
	ErrUserExists       = errors.New("auth: user already exists")
	ErrInvalidCreds     = errors.New("auth: invalid credentials")
	ErrInvalidToken     = errors.New("auth: invalid token")
	ErrForbidden        = errors.New("auth: forbidden")
	ErrInvalidRole      = errors.New("auth: invalid role")
	ErrWeakPassword     = errors.New("auth: password too short")
	ErrInvalidUsername  = errors.New("auth: invalid username")
)
