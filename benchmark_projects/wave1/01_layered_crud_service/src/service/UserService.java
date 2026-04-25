package service;

import java.util.List;
import model.User;
import repository.UserRepository;

public class UserService {
    private final UserRepository repository;
    private final UserValidator validator;

    public UserService(UserRepository repository, UserValidator validator) {
        this.repository = repository;
        this.validator = validator;
    }

    public void create(User user) {
        validator.validate(user);
        repository.save(user);
    }

    public User getById(int id) {
        return repository.findById(id);
    }

    public List<User> listAll() {
        return repository.findAll();
    }
}
