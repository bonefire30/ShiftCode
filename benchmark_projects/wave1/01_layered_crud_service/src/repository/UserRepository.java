package repository;

import java.util.List;
import model.User;

public interface UserRepository {
    void save(User user);

    User findById(int id);

    List<User> findAll();
}
