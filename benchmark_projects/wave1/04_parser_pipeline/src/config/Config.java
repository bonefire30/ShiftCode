package config;

import java.util.Collections;
import java.util.HashMap;
import java.util.Map;

public class Config {
    private final Map<String, String> values = new HashMap<String, String>();

    public void put(String key, String value) {
        values.put(key, value);
    }

    public String get(String key) {
        return values.get(key);
    }

    public Map<String, String> asMap() {
        return Collections.unmodifiableMap(values);
    }
}
