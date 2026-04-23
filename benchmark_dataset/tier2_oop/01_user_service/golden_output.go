// golden_output.go — reference Go implementation; use with evaluate.py --use-golden
// to verify the evaluation harness without an LLM.

package userservice

import (
	"errors"
	"fmt"
	"strings"
)

// UserService holds connection metadata migrated from the Java class.
type UserService struct {
	dbConnection string
}

// NewUserService returns a service; empty dbConnection is invalid.
func NewUserService(dbConnection string) (*UserService, error) {
	s := strings.TrimSpace(dbConnection)
	if s == "" {
		return nil, errors.New("db connection must be non-empty")
	}
	return &UserService{dbConnection: s}, nil
}

// DBConnection returns the bound connection string (mirrors Java getter).
func (s *UserService) DBConnection() string {
	if s == nil {
		return ""
	}
	return s.dbConnection
}

// GetUserStatus maps Java getUserStatus: negative age is an error.
func (s *UserService) GetUserStatus(age int) (string, error) {
	if age < 0 {
		return "", fmt.Errorf("age cannot be negative")
	}
	if age >= 18 {
		return "Adult", nil
	}
	return "Minor", nil
}
