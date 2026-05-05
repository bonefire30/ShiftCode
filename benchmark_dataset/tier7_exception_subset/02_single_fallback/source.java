public class FallbackReader {
    public String read(String primary) {
        try {
            return fetch(primary);
        } catch (RuntimeException e) {
            return "fallback";
        }
    }

    private String fetch(String value) {
        if (value == null) {
            throw new RuntimeException("missing");
        }
        return value;
    }
}
