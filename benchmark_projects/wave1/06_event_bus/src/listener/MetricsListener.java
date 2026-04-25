package listener;

import event.Event;
import event.EventListener;

public class MetricsListener implements EventListener {
    private int seenCount;

    @Override
    public void onEvent(Event event) {
        seenCount++;
    }

    public int getSeenCount() {
        return seenCount;
    }
}
