package event;

public class UserCreatedEvent implements Event {
    private final int userId;

    public UserCreatedEvent(int userId) {
        this.userId = userId;
    }

    public int getUserId() {
        return userId;
    }

    @Override
    public String type() {
        return "user.created";
    }
}
