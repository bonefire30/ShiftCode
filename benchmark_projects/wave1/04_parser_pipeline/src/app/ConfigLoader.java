package app;

import config.Config;
import config.ConfigParser;
import config.ConfigSource;
import util.ValidationUtil;

public class ConfigLoader {
    private final ConfigSource source;
    private final ConfigParser parser;
    private final ValidationUtil validation;

    public ConfigLoader(ConfigSource source, ConfigParser parser, ValidationUtil validation) {
        this.source = source;
        this.parser = parser;
        this.validation = validation;
    }

    public Config load() {
        Config config = parser.parse(source.load());
        validation.requireConnectionFields(config);
        return config;
    }
}
