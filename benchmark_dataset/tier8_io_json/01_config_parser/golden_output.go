// golden_output.go — reference Go for evaluate.py --use-golden

package configparser

import (
	"encoding/json"
	"io"
)

// AppConfig matches JSON keys; Internal uses json:"-" so it is not unmarshaled.
type AppConfig struct {
	DBUrl    string `json:"db_url"`
	Internal string `json:"-"`
}

// ParseConfig reads a JSON object from r into AppConfig.
func ParseConfig(r io.Reader) (*AppConfig, error) {
	var c AppConfig
	dec := json.NewDecoder(r)
	if err := dec.Decode(&c); err != nil {
		return nil, err
	}
	return &c, nil
}
