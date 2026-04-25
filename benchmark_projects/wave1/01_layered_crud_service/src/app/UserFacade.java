package app;

import java.util.List;
import model.User;
import repository.UserRepository;
import service.UserService;
import service.UserValidator;

public class UserFacade {
    private final UserService service;

    public UserFacade(UserRepository repository) {
        this.service = new UserService(repository, new UserValidator());
    }

    public void createUser(int id, String name, String email) {
        service.create(new User(id, name, email));
    }

    public User getUser(int id) {
        return service.getById(id);
    }

    public List<User> listUsers() {
        return service.listAll();
    }
}
