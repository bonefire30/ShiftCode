/**
 * Tier7: retry loop with nested try/catch/finally and distinct exception types.
 * Migration: errors.Is, explicit err handling, defer for cleanup.
 */
public class RetryExecutor {

    public static class NetworkException extends Exception {
    }

    public static class AuthException extends Exception {
    }

    public interface Task {
        void run() throws Exception;
    }

    private int cleanupCount;

    public int getCleanupCount() {
        return cleanupCount;
    }

    public int runWithRetry(Task task, int maxAttempts) throws Exception {
        int attempt = 0;
        while (true) {
            try {
                attempt++;
                task.run();
                return attempt;
            } catch (NetworkException e) {
                if (attempt >= maxAttempts) {
                    throw e;
                }
            } catch (AuthException e) {
                throw e;
            } finally {
                cleanupCount++;
            }
        }
    }
}
