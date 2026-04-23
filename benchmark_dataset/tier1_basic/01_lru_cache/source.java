import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Least-Recently-Used cache with fixed capacity.
 * Backed by access-ordered {@link LinkedHashMap}; evicts oldest on overflow.
 */
public class LRUCache {
    private final int capacity;
    private final LinkedHashMap<Integer, Integer> map;

    public LRUCache(int capacity) {
        if (capacity < 1) {
            throw new IllegalArgumentException("capacity must be >= 1");
        }
        this.capacity = capacity;
        this.map = new LinkedHashMap<Integer, Integer>(16, 0.75f, true) {
            @Override
            protected boolean removeEldestEntry(Map.Entry<Integer, Integer> eldest) {
                return size() > LRUCache.this.capacity;
            }
        };
    }

    /**
     * Return value for key, or -1 if missing.
     */
    public int get(int key) {
        Integer v = map.get(key);
        if (v == null) {
            return -1;
        }
        return v.intValue();
    }

    public void put(int key, int value) {
        map.put(key, value);
    }
}
