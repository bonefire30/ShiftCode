import java.util.*;
import java.util.concurrent.*;

/**
 * Simulates parallel HTTP fetches: fixed thread pool, latch, concurrent map.
 * Migration target: Go goroutines, {@code sync.WaitGroup}, mutex-protected map.
 */
public class BatchDownloader {

    /**
     * Run mock downloads for each URL concurrently; blocks until all complete or timeout.
     * @return a map of URL to body (each body is "ok:" + url).
     */
    public static Map<String, String> downloadAll(List<String> urls) throws Exception {
        if (urls == null) {
            throw new IllegalArgumentException("urls is null");
        }
        Map<String, String> out = new ConcurrentHashMap<>();
        if (urls.isEmpty()) {
            return out;
        }
        ExecutorService pool = Executors.newFixedThreadPool(4);
        CountDownLatch done = new CountDownLatch(urls.size());
        for (String u : urls) {
            final String url = u;
            pool.submit(() -> {
                try {
                    out.put(url, mockFetch(url));
                } finally {
                    done.countDown();
                }
            });
        }
        if (!done.await(30, TimeUnit.SECONDS)) {
            pool.shutdownNow();
            throw new IllegalStateException("download timeout");
        }
        pool.shutdown();
        return out;
    }

    static String mockFetch(String url) {
        return "ok:" + url;
    }
}
