import java.util.Map;

public class ConfigLookup {
    public static String host(Map<String, String> config) {
        return config.get("host");
    }
}
