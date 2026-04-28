package simplemethod

type SimpleGreeter struct{}

func (s *SimpleGreeter) Greet(name string) string {
	return "Hello, " + name
}
