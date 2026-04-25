package client;

public class RetryPolicy {
    private final int maxAttempts;

    public RetryPolicy(int maxAttempts) {
        this.maxAttempts = maxAttempts;
    }

    public int getMaxAttempts() {
        return maxAttempts;
    }

    public boolean shouldRetry(int statusCode) {
        return statusCode >= 500;
    }
}
