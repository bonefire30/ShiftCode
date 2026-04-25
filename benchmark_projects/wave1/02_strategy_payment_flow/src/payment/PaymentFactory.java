package payment;

public class PaymentFactory {
    public PaymentMethod create(String method) {
        if ("credit".equals(method)) {
            return new CreditCardPayment();
        }
        if ("paypal".equals(method)) {
            return new PaypalPayment();
        }
        throw new IllegalArgumentException("unsupported method: " + method);
    }
}
