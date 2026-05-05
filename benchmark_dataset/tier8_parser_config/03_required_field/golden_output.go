package parserconfig

import "fmt"

func Validate(config map[string]string) error {
	value, ok := config["host"]
	if !ok || value == "" {
		return fmt.Errorf("host is required")
	}
	return nil
}
