package listener;

import java.util.ArrayList;
import java.util.List;
import event.Event;
import event.EventListener;

public class AuditListener implements EventListener {
    private final List<String> entries = new ArrayList<String>();

    @Override
    public void onEvent(Event event) {
        entries.add("audit:" + event.type());
    }

    public List<String> getEntries() {
        return new ArrayList<String>(entries);
    }
}
