package lrucache

import "container/list"

// LRUCache is a least-recently-used cache with fixed capacity.
type LRUCache struct {
	cap  int
	m    map[int]*list.Element
	list *list.List
}

type pair struct{ key, val int }

// NewLRUCache panics if capacity < 1.
func NewLRUCache(capacity int) *LRUCache {
	if capacity < 1 {
		panic("capacity must be >= 1")
	}
	return &LRUCache{
		cap:  capacity,
		m:    make(map[int]*list.Element),
		list: list.New(),
	}
}

// Get returns the value for key, or -1 if missing. Access marks key as recently used.
func (c *LRUCache) Get(key int) int {
	if e, ok := c.m[key]; ok {
		c.list.MoveToFront(e)
		return e.Value.(*pair).val
	}
	return -1
}

// Put inserts or updates a key. Evicts least-recently-used when at capacity.
func (c *LRUCache) Put(key, value int) {
	if e, ok := c.m[key]; ok {
		e.Value.(*pair).val = value
		c.list.MoveToFront(e)
		return
	}
	if c.list.Len() == c.cap {
		back := c.list.Back()
		if back != nil {
			old := back.Value.(*pair)
			delete(c.m, old.key)
			c.list.Remove(back)
		}
	}
	ne := c.list.PushFront(&pair{key: key, val: value})
	c.m[key] = ne
}
