package exceptionflow

import (
	"fmt"
	"strconv"
)

func ParseTimeout(raw string) (int, error) {
	value, err := strconv.Atoi(raw)
	if err != nil {
		return 0, fmt.Errorf("timeout is invalid")
	}
	return value, nil
}
