package auth

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
	"golang.org/x/crypto/bcrypt"

	"github.com/jakkrit-ch/trading-ai-v2/backend/internal/platform/ids"
)

// Config controls JWT signing.
type Config struct {
	JWTSecret string
	JWTTTL    time.Duration
	Issuer    string
}

// Claims is the JWT payload.
type Claims struct {
	UserID   string `json:"uid"`
	Username string `json:"usr"`
	Role     Role   `json:"role"`
	jwt.RegisteredClaims
}

// Service provides registration, login, and token verification.
type Service struct {
	repo Repo
	cfg  Config
	now  func() time.Time
}

func NewService(repo Repo, cfg Config) *Service {
	if cfg.JWTTTL <= 0 {
		cfg.JWTTTL = 24 * time.Hour
	}
	if cfg.Issuer == "" {
		cfg.Issuer = "trading-ai-v2"
	}
	return &Service{repo: repo, cfg: cfg, now: func() time.Time { return time.Now().UTC() }}
}

// Register creates a new user. Returns the persisted public projection.
func (s *Service) Register(ctx context.Context, username, password string, role Role) (PublicUser, error) {
	username = strings.TrimSpace(strings.ToLower(username))
	if len(username) < 3 {
		return PublicUser{}, ErrInvalidUsername
	}
	if len(password) < 8 {
		return PublicUser{}, ErrWeakPassword
	}
	if role == "" {
		role = RoleViewer
	}
	if !role.Valid() {
		return PublicUser{}, ErrInvalidRole
	}
	hash, err := bcrypt.GenerateFromPassword([]byte(password), bcrypt.DefaultCost)
	if err != nil {
		return PublicUser{}, fmt.Errorf("auth: hash password: %w", err)
	}
	u := User{
		ID:           ids.New(),
		Username:     username,
		PasswordHash: string(hash),
		Role:         role,
		CreatedAt:    s.now(),
		UpdatedAt:    s.now(),
	}
	if err := s.repo.Create(ctx, u); err != nil {
		return PublicUser{}, err
	}
	return u.Public(), nil
}

// Login validates credentials and returns a signed JWT plus the user.
func (s *Service) Login(ctx context.Context, username, password string) (string, PublicUser, error) {
	u, err := s.repo.GetByUsername(ctx, username)
	if err != nil {
		if errors.Is(err, ErrUserNotFound) {
			return "", PublicUser{}, ErrInvalidCreds
		}
		return "", PublicUser{}, err
	}
	if err := bcrypt.CompareHashAndPassword([]byte(u.PasswordHash), []byte(password)); err != nil {
		return "", PublicUser{}, ErrInvalidCreds
	}
	tok, err := s.IssueToken(u)
	if err != nil {
		return "", PublicUser{}, err
	}
	return tok, u.Public(), nil
}

// IssueToken signs a JWT for the given user.
func (s *Service) IssueToken(u User) (string, error) {
	if s.cfg.JWTSecret == "" {
		return "", fmt.Errorf("auth: jwt secret not configured")
	}
	now := s.now()
	claims := Claims{
		UserID:   u.ID,
		Username: u.Username,
		Role:     u.Role,
		RegisteredClaims: jwt.RegisteredClaims{
			Issuer:    s.cfg.Issuer,
			Subject:   u.ID,
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(s.cfg.JWTTTL)),
		},
	}
	tok := jwt.NewWithClaims(jwt.SigningMethodHS256, claims)
	signed, err := tok.SignedString([]byte(s.cfg.JWTSecret))
	if err != nil {
		return "", fmt.Errorf("auth: sign token: %w", err)
	}
	return signed, nil
}

// VerifyToken parses and validates a token string. Returns the embedded claims.
func (s *Service) VerifyToken(tokenStr string) (*Claims, error) {
	if s.cfg.JWTSecret == "" {
		return nil, fmt.Errorf("auth: jwt secret not configured")
	}
	claims := &Claims{}
	tok, err := jwt.ParseWithClaims(tokenStr, claims, func(t *jwt.Token) (interface{}, error) {
		if _, ok := t.Method.(*jwt.SigningMethodHMAC); !ok {
			return nil, fmt.Errorf("unexpected signing method: %v", t.Header["alg"])
		}
		return []byte(s.cfg.JWTSecret), nil
	})
	if err != nil || !tok.Valid {
		return nil, ErrInvalidToken
	}
	if !claims.Role.Valid() {
		return nil, ErrInvalidToken
	}
	return claims, nil
}

// Me returns the current user by id.
func (s *Service) Me(ctx context.Context, userID string) (PublicUser, error) {
	u, err := s.repo.GetByID(ctx, userID)
	if err != nil {
		return PublicUser{}, err
	}
	return u.Public(), nil
}
