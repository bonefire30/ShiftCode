// golden_output.go — reference Go for evaluate.py --use-golden

package dataanalyzer

// Person is a row from the Java DataAnalyzer.Person class.
type Person struct {
	Name       string
	Age        int
	Department string
}

// GroupAdultNamesByDepartment returns department -> adult names (age > 18 only).
func GroupAdultNamesByDepartment(people []Person) map[string][]string {
	out := make(map[string][]string)
	if people == nil {
		return out
	}
	for _, p := range people {
		if p.Age <= 18 {
			continue
		}
		out[p.Department] = append(out[p.Department], p.Name)
	}
	return out
}
