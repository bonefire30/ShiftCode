import java.util.Map;

public class ConfigDefaults {
    public static String port(Map<String, String> config) {
        return config.getOrDefault("port", "8080");
    }
}
