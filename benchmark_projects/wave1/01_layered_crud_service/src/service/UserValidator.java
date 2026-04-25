package service;

import model.User;

public class UserValidator {
    public void validate(User user) {
        if (user == null) {
            throw new IllegalArgumentException("user is required");
        }
        if (isBlank(user.getName())) {
            throw new IllegalArgumentException("name is required");
        }
        if (isBlank(user.getEmail())) {
            throw new IllegalArgumentException("email is required");
        }
    }

    private boolean isBlank(String value) {
        return value == null || value.trim().isEmpty();
    }
}
