package exceptionflow

func RunWithRetry(run func() (string, error), maxAttempts int) (string, error) {
	attempt := 0
	for {
		value, err := run()
		if err == nil {
			return value, nil
		}
		attempt++
		if attempt >= maxAttempts {
			return "", err
		}
	}
}
