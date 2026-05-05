package parserconfig

func Port(config map[string]string) string {
	if value, ok := config["port"]; ok {
		return value
	}
	return "8080"
}
