import java.util.*;
import java.util.stream.Collectors;

/**
 * Tier6: Java Stream filter + grouping. Migration: explicit loops or maps/slices helpers in Go.
 */
public class DataAnalyzer {

    public static class Person {
        public String name;
        public int age;
        public String department;

        public Person(String name, int age, String department) {
            this.name = name;
            this.age = age;
            this.department = department;
        }
    }

    public static Map<String, List<String>> groupAdultNamesByDepartment(List<Person> people) {
        if (people == null) {
            return new HashMap<>();
        }
        return people.stream()
                .filter(p -> p.age > 18)
                .collect(Collectors.groupingBy(
                        p -> p.department,
                        Collectors.mapping(p -> p.name, Collectors.toList())));
    }
}
