// golden_output.go — reference Go for evaluate.py --use-golden

package retryexec

import "errors"

// Sentinel errors aligned with Java NetworkException / AuthException.
var ErrNetwork = errors.New("network")
var ErrAuth = errors.New("auth")

// RetryExecutor tracks per-attempt cleanup like Java finally.
type RetryExecutor struct {
	cleanupCount int
}

// CleanupCount returns how many attempt bodies completed (finally runs).
func (e *RetryExecutor) CleanupCount() int {
	return e.cleanupCount
}

// RunWithRetry mirrors the Java control flow.
func (e *RetryExecutor) RunWithRetry(op func() error, maxAttempts int) (int, error) {
	attempt := 0
	for {
		attempt++
		var err error
		func() {
			defer func() { e.cleanupCount++ }()
			err = op()
		}()
		if err == nil {
			return attempt, nil
		}
		if errors.Is(err, ErrAuth) {
			return attempt, err
		}
		if errors.Is(err, ErrNetwork) {
			if attempt >= maxAttempts {
				return attempt, err
			}
			continue
		}
		return attempt, err
	}
}
