package event;

import java.util.ArrayList;
import java.util.List;

public class EventBus {
    private final List<EventListener> listeners = new ArrayList<EventListener>();

    public void register(EventListener listener) {
        listeners.add(listener);
    }

    public void publish(Event event) {
        for (EventListener listener : listeners) {
            listener.onEvent(event);
        }
    }
}
