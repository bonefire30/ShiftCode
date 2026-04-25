package payment;

import java.util.ArrayList;
import java.util.List;

public class PaymentLogger {
    private final List<String> entries = new ArrayList<String>();

    public void log(String method, int amount) {
        entries.add(method + " processed " + amount);
    }

    public List<String> entries() {
        return new ArrayList<String>(entries);
    }
}
