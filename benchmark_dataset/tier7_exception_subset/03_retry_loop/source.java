public class RetryFlow {
    interface Task {
        String run() throws Exception;
    }

    public String runWithRetry(Task task, int maxAttempts) throws Exception {
        int attempt = 0;
        while (true) {
            try {
                return task.run();
            } catch (Exception e) {
                attempt++;
                if (attempt >= maxAttempts) {
                    throw e;
                }
            }
        }
    }
}
