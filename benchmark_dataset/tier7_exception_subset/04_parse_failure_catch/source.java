public class SafeParse {
    public int parseTimeout(String raw) {
        try {
            return Integer.parseInt(raw);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("timeout is invalid");
        }
    }
}
