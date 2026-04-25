package config;

import util.StringUtil;

public class ConfigParser {
    public Config parse(String text) {
        Config config = new Config();
        String[] lines = text.split("\\n");
        for (String rawLine : lines) {
            String line = StringUtil.trim(rawLine);
            if (line.isEmpty()) {
                continue;
            }
            String[] parts = line.split("=", 2);
            if (parts.length == 2) {
                config.put(StringUtil.trim(parts[0]), StringUtil.trim(parts[1]));
            }
        }
        return config;
    }
}
