package exceptionflow

import "fmt"

func ValidateAge(age int) error {
	if age < 0 {
		return fmt.Errorf("age cannot be negative")
	}
	return nil
}
