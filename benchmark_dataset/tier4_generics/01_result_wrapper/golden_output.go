// golden_output.go — reference Go for evaluate.py --use-golden

package resultwrap

// Result is a success/failure pair migrated from Java Result<T, E>.
type Result[T, E any] struct {
	ok  bool
	val T
	err E
}

// NewSuccess builds a success Result; Err() returns zero E.
func NewSuccess[T, E any](v T) Result[T, E] {
	var zeroE E
	return Result[T, E]{ok: true, val: v, err: zeroE}
}

// NewFailure builds a failure Result; Value() returns zero T.
func NewFailure[T, E any](e E) Result[T, E] {
	var zeroT T
	return Result[T, E]{ok: false, val: zeroT, err: e}
}

// IsSuccess reports whether the operation succeeded.
func (r Result[T, E]) IsSuccess() bool { return r.ok }

// Value returns the success payload.
func (r Result[T, E]) Value() T { return r.val }

// Err returns the failure value (or zero on success).
func (r Result[T, E]) Err() E { return r.err }

// FilterNonNull returns a new slice with nil elements removed. Nil slice input yields empty non-nil slice.
func FilterNonNull[T any](items []*T) []*T {
	if items == nil {
		return []*T{}
	}
	out := make([]*T, 0, len(items))
	for _, p := range items {
		if p != nil {
			out = append(out, p)
		}
	}
	return out
}
