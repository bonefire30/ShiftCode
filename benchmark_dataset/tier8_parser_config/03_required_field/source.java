import java.util.Map;

public class ConfigValidation {
    public static void validate(Map<String, String> config) {
        if (!config.containsKey("host") || config.get("host") == null) {
            throw new IllegalArgumentException("host is required");
        }
    }
}
