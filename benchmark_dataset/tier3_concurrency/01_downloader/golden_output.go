package downloader

import (
	"errors"
	"sync"
)

func mockFetch(url string) string {
	return "ok:" + url
}

// DownloadAll runs mockFetch for each URL concurrently and returns url -> body.
// Returns a non-nil error if urls is nil; empty slice yields an empty map.
func DownloadAll(urls []string) (map[string]string, error) {
	if urls == nil {
		return nil, errors.New("urls is null")
	}
	out := make(map[string]string)
	if len(urls) == 0 {
		return out, nil
	}
	var wg sync.WaitGroup
	var mu sync.Mutex
	for _, u := range urls {
		u := u
		wg.Add(1)
		go func() {
			defer wg.Done()
			v := mockFetch(u)
			mu.Lock()
			out[u] = v
			mu.Unlock()
		}()
	}
	wg.Wait()
	return out, nil
}
