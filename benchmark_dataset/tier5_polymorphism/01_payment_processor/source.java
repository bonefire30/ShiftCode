/**
 * Tier5: abstract payment type with subclasses (Java inheritance).
 * Migration target: Go interfaces + concrete structs.
 */
public class PaymentProcessor {

    public static abstract class AbstractPayment {
        protected int id;

        public AbstractPayment(int id) {
            this.id = id;
        }

        public int getId() {
            return id;
        }

        public void logTransaction() {
        }

        public abstract String process();
    }

    public static class CreditCardPayment extends AbstractPayment {
        public CreditCardPayment(int id) {
            super(id);
        }

        @Override
        public String process() {
            logTransaction();
            return "credit";
        }
    }

    public static class PaypalPayment extends AbstractPayment {
        public PaypalPayment(int id) {
            super(id);
        }

        @Override
        public String process() {
            logTransaction();
            return "paypal";
        }
    }

    public static String runPayment(AbstractPayment p) {
        return p.process();
    }
}
