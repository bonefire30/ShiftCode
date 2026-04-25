package app;

import event.EventBus;
import event.UserCreatedEvent;

public class UserRegistrationService {
    private final EventBus eventBus;

    public UserRegistrationService(EventBus eventBus) {
        this.eventBus = eventBus;
    }

    public int register(int userId) {
        eventBus.publish(new UserCreatedEvent(userId));
        return userId;
    }
}
