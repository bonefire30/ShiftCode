package repository;

import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import model.User;

public class InMemoryUserRepository implements UserRepository {
    private final Map<Integer, User> users = new HashMap<Integer, User>();

    @Override
    public void save(User user) {
        users.put(user.getId(), user);
    }

    @Override
    public User findById(int id) {
        return users.get(id);
    }

    @Override
    public List<User> findAll() {
        return new ArrayList<User>(users.values());
    }
}
