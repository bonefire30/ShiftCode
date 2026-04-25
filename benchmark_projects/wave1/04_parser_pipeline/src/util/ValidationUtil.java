package util;

import config.Config;

public class ValidationUtil {
    public void requireConnectionFields(Config config) {
        if (StringUtil.trim(config.get("host")).isEmpty()) {
            throw new IllegalArgumentException("host is required");
        }
        if (StringUtil.trim(config.get("port")).isEmpty()) {
            throw new IllegalArgumentException("port is required");
        }
    }
}
