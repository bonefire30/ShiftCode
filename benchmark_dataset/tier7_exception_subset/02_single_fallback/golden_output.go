package exceptionflow

func Read(primary string) string {
	if primary == "" {
		return "fallback"
	}
	return primary
}
