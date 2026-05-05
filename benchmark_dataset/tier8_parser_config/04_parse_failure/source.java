import java.util.Map;

public class ConfigParseFailure {
    public static int timeout(Map<String, String> config) {
        return Integer.parseInt(config.get("timeout"));
    }
}
