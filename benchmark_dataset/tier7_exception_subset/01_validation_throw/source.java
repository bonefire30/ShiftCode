public class UserValidation {
    public static void validateAge(int age) {
        if (age < 0) {
            throw new IllegalArgumentException("age cannot be negative");
        }
    }
}
