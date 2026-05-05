package parserconfig

import "strconv"

func Timeout(config map[string]string) (int, error) {
	return strconv.Atoi(config["timeout"])
}
