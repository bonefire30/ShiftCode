/**
 * Tier2 OOP benchmark: class with constructor, private field, and checked exceptions.
 * Migration target: Go struct, constructor NewUserService, (string, error) for domain errors.
 */
public class UserService {
    private final String dbConnection;

    public UserService(String dbConnection) {
        if (dbConnection == null || dbConnection.isEmpty()) {
            throw new IllegalArgumentException("db connection must be non-empty");
        }
        this.dbConnection = dbConnection;
    }

    public String getUserStatus(int age) throws Exception {
        if (age < 0) {
            throw new Exception("age cannot be negative");
        }
        if (age >= 18) {
            return "Adult";
        }
        return "Minor";
    }

    // Intentional getter for OOP / encapsulation; migration may expose or omit.
    public String getDbConnection() {
        return this.dbConnection;
    }
}
